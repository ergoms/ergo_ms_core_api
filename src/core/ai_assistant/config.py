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
    """

    provider: LLMProvider = LLMProvider.AUTO
    model: str = getattr(settings, "OLLAMA_DEFAULT_MODEL", "mistral:7b")
    base_url: str = getattr(settings, "OLLAMA_BASE_URL", "http://localhost:11434")
    request_timeout: float = getattr(settings, "AI_ASSISTANT_REQUEST_TIMEOUT", 180.0)  # Увеличено до 3 минут
    stream_timeout: float = getattr(settings, "AI_ASSISTANT_STREAM_TIMEOUT", 300.0)  # Увеличено до 5 минут для streaming
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
            data["provider"] = LLMProvider(data["provider"])
        if isinstance(data["compute_device"], str):
            data["compute_device"] = ComputeDevice(data["compute_device"])

        data["provider_config"].update(provider_overrides)
        data["device_config"].update(device_overrides)

        return RuntimeLLMConfig(**data)


def _inject_env_defaults(config: RuntimeLLMConfig) -> RuntimeLLMConfig:
    """Пополняет конфигурацию значениями из переменных окружения."""
    env_base_url = os.getenv("OLLAMA_BASE_URL") or os.getenv("OLLAMA_API_BASE")
    if env_base_url:
        config.base_url = env_base_url

    if config.base_url and not config.provider_config.get("base_url"):
        config.provider_config["base_url"] = config.base_url

    # В зависимости от выбранного устройства заполняем device_config (используется в HTTP клиенте)
    if config.compute_device == ComputeDevice.CPU:
        config.device_config.setdefault("num_gpu", 0)
    else:
        config.device_config.setdefault("num_gpu", -1)

    return config


def build_runtime_config(overrides: Optional[Dict[str, Any]] = None) -> RuntimeLLMConfig:
    """Формирует итоговую конфигурацию с учётом environment и module-config."""
    base_config = RuntimeLLMConfig()
    config = base_config.copy_with_overrides(overrides)
    config = _inject_env_defaults(config)

    config.provider = LLMProvider.OLLAMA
    return config


