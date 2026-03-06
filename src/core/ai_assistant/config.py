from __future__ import annotations

import os
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, Optional

from django.conf import settings


class ComputeDevice(str, Enum):
    """Тип вычислительного устройства для LLM."""

    GPU = "gpu"
    CPU = "cpu"


class LLMProvider(str, Enum):
    """Доступные провайдеры LLM."""

    AUTO = "auto"
    OLLAMA = "ollama"


@dataclass
class RuntimeLLMConfig:
    """
    Конфигурация запуска LLM с поддержкой переопределения через module-config.

    provider_config – дополнительные параметры конкретного провайдера (API ключи и т.д.).
    device_config – дополнительные параметры для выбора устройства (например GPU id).
    
    Поддерживаемый провайдер:
    - ollama (по умолчанию) - Ollama сервер
    
    Переключение через env: LLM_PROVIDER=ollama
    """

    provider: LLMProvider = LLMProvider.AUTO
    model: Optional[str] = getattr(settings, "OLLAMA_DEFAULT_MODEL", None)
    base_url: Optional[str] = getattr(settings, "OLLAMA_BASE_URL", None)
    request_timeout: float = getattr(settings, "AI_ASSISTANT_REQUEST_TIMEOUT", 180.0)
    stream_timeout: float = getattr(settings, "AI_ASSISTANT_STREAM_TIMEOUT", 300.0)
    compute_device: ComputeDevice = ComputeDevice.GPU
    sql_tokens: int = getattr(settings, "AI_ASSISTANT_SQL_TOKENS", 256)
    commentary_tokens: int = getattr(settings, "AI_ASSISTANT_COMMENTARY_TOKENS", 192)
    temperature_sql: float = getattr(settings, "AI_ASSISTANT_TEMPERATURE_SQL", 0.08)
    temperature_commentary: float = getattr(settings, "AI_ASSISTANT_TEMPERATURE_COMMENTARY", 0.24)
    concurrency_limit: int = getattr(settings, "AI_ASSISTANT_CONCURRENCY_LIMIT", 8)
    max_retries: int = getattr(settings, "AI_ASSISTANT_MAX_RETRIES", 2)
    keep_alive: str = getattr(settings, "AI_ASSISTANT_KEEP_ALIVE", "10m")
    provider_config: Dict[str, Any] = field(default_factory=dict)
    device_config: Dict[str, Any] = field(default_factory=dict)

    def copy_with_overrides(self, overrides: Optional[Dict[str, Any]] = None) -> "RuntimeLLMConfig":
        """Создает копию конфигурации с учётом переопределений из module-config."""
        if not overrides:
            return self

        data: Dict[str, Any] = {
            "provider": self.provider,
            "model": self.model,
            "base_url": self.base_url,
            "request_timeout": self.request_timeout,
            "stream_timeout": self.stream_timeout,
            "compute_device": self.compute_device,
            "sql_tokens": self.sql_tokens,
            "commentary_tokens": self.commentary_tokens,
            "temperature_sql": self.temperature_sql,
            "temperature_commentary": self.temperature_commentary,
            "concurrency_limit": self.concurrency_limit,
            "max_retries": self.max_retries,
            "keep_alive": self.keep_alive,
            "provider_config": dict(self.provider_config),
            "device_config": dict(self.device_config),
        }

        provider_overrides: Dict[str, Any] = {}
        device_overrides: Dict[str, Any] = {}

        for key, value in overrides.items():
            if key in data:
                data[key] = value
            elif key.startswith("provider__"):
                provider_overrides[key.split("__", 1)[1]] = value
            elif key.startswith("device__"):
                device_overrides[key.split("__", 1)[1]] = value
            else:
                # Всё прочее относится к провайдеру (API ключи, параметры генерации)
                provider_overrides[key] = value

        if isinstance(data["provider"], str):
            p = data["provider"].lower()
            data["provider"] = LLMProvider.OLLAMA if p == "llama_cpp" else LLMProvider(p)
        if isinstance(data["compute_device"], str):
            data["compute_device"] = ComputeDevice(data["compute_device"])

        data["provider_config"].update(provider_overrides)
        data["device_config"].update(device_overrides)

        return RuntimeLLMConfig(**data)


def _inject_env_defaults(config: RuntimeLLMConfig) -> RuntimeLLMConfig:
    """Пополняет конфигурацию значениями из переменных окружения."""
    
    # Определяем провайдера из env
    env_provider = os.getenv("LLM_PROVIDER", "").lower()
    if env_provider == "llama_cpp":
        # llama.cpp удалён — fallback на Ollama
        config.provider = LLMProvider.OLLAMA
    elif env_provider == "ollama":
        config.provider = LLMProvider.OLLAMA
    
    # Настройки для Ollama
    if config.provider in (LLMProvider.AUTO, LLMProvider.OLLAMA):
        env_base_url = os.getenv("OLLAMA_BASE_URL") or os.getenv("OLLAMA_API_BASE")
        if env_base_url:
            config.base_url = env_base_url
        
        env_model = os.getenv("OLLAMA_DEFAULT_MODEL")
        if env_model:
            config.model = env_model

    if config.base_url and not config.provider_config.get("base_url"):
        config.provider_config["base_url"] = config.base_url

    # В зависимости от выбранного устройства заполняем device_config
    if config.compute_device == ComputeDevice.CPU:
        config.device_config.setdefault("num_gpu", 0)
    else:
        config.device_config.setdefault("num_gpu", -1)

    return config


_FALLBACK_CONFIG = {
    "provider": LLMProvider.OLLAMA,
    "model": "llama2",
    "base_url": "http://localhost:11434",
    "request_timeout": 180.0,
    "stream_timeout": 300.0,
    "compute_device": ComputeDevice.GPU,
    "concurrency_limit": 8,
    "max_retries": 2,
    "keep_alive": "10m",
    "provider_config": {},
    "device_config": {},
}


def build_runtime_config(
    overrides: Optional[Dict[str, Any]] = None,
    skip_env_injection: bool = False,
) -> RuntimeLLMConfig:
    """
    Формирует итоговую конфигурацию с учётом environment и module-config.

    Args:
        overrides: переопределения из module-config.
        skip_env_injection: если True — не применять настройки ядра и env,
            использовать только overrides с минимальными fallback-значениями.
            Нужно для модулей с собственным settings (например, technical_process_analysis).

    Провайдер определяется через:
    1. Параметр overrides['provider']
    2. Переменную окружения LLM_PROVIDER (ollama) — только если skip_env_injection=False
    3. По умолчанию - ollama
    """
    if skip_env_injection:
        base_config = RuntimeLLMConfig(**_FALLBACK_CONFIG)
        config = base_config.copy_with_overrides(overrides)
        if config.base_url and not config.provider_config.get("base_url"):
            config.provider_config["base_url"] = config.base_url
        if config.compute_device == ComputeDevice.CPU:
            config.device_config.setdefault("num_gpu", 0)
        else:
            config.device_config.setdefault("num_gpu", -1)
    else:
        base_config = RuntimeLLMConfig()
        config = base_config.copy_with_overrides(overrides)
        config = _inject_env_defaults(config)

    if config.provider == LLMProvider.AUTO:
        config.provider = LLMProvider.OLLAMA

    return config


