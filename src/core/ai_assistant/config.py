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
    LLAMA_CPP = "llama_cpp"


@dataclass
class RuntimeLLMConfig:
    """
    Конфигурация запуска LLM с поддержкой переопределения через module-config.

    provider_config – дополнительные параметры конкретного провайдера (API ключи и т.д.).
    device_config – дополнительные параметры для выбора устройства (например GPU id).
    
    Поддерживаемые провайдеры:
    - ollama (по умолчанию) - Ollama сервер
    - llama_cpp - llama.cpp сервер
    
    Переключение через env: LLM_PROVIDER=ollama|llama_cpp
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
    
    # Настройки llama.cpp
    llama_cpp_gpu_layers: int = 35  # Количество слоёв на GPU
    llama_cpp_threads: int = 8  # Количество потоков CPU
    llama_cpp_context_size: int = 4096  # Размер контекста
    llama_cpp_batch_size: int = 512  # Размер батча

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
            "llama_cpp_gpu_layers": self.llama_cpp_gpu_layers,
            "llama_cpp_threads": self.llama_cpp_threads,
            "llama_cpp_context_size": self.llama_cpp_context_size,
            "llama_cpp_batch_size": self.llama_cpp_batch_size,
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
    
    # Определяем провайдера из env
    env_provider = os.getenv("LLM_PROVIDER", "").lower()
    if env_provider == "llama_cpp":
        config.provider = LLMProvider.LLAMA_CPP
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
    
    # Настройки для llama.cpp
    if config.provider == LLMProvider.LLAMA_CPP:
        env_base_url = os.getenv("LLAMA_CPP_BASE_URL", "http://localhost:8080")
        config.base_url = env_base_url
        
        env_model = os.getenv("LLAMA_CPP_MODEL")
        if env_model:
            config.model = env_model
        
        # GPU layers
        env_gpu_layers = os.getenv("LLAMA_CPP_GPU_LAYERS")
        if env_gpu_layers:
            config.llama_cpp_gpu_layers = int(env_gpu_layers)
        
        # Threads
        env_threads = os.getenv("LLAMA_CPP_THREADS")
        if env_threads:
            config.llama_cpp_threads = int(env_threads)
        
        # Context size
        env_ctx = os.getenv("LLAMA_CPP_CONTEXT_SIZE")
        if env_ctx:
            config.llama_cpp_context_size = int(env_ctx)
        
        # Batch size
        env_batch = os.getenv("LLAMA_CPP_BATCH_SIZE")
        if env_batch:
            config.llama_cpp_batch_size = int(env_batch)
        
        # Добавляем настройки в device_config для llama.cpp
        config.device_config["n_gpu_layers"] = config.llama_cpp_gpu_layers
        config.device_config["n_threads"] = config.llama_cpp_threads

    if config.base_url and not config.provider_config.get("base_url"):
        config.provider_config["base_url"] = config.base_url

    # В зависимости от выбранного устройства заполняем device_config
    if config.compute_device == ComputeDevice.CPU:
        config.device_config.setdefault("num_gpu", 0)
        if config.provider == LLMProvider.LLAMA_CPP:
            config.device_config["n_gpu_layers"] = 0
    else:
        config.device_config.setdefault("num_gpu", -1)

    return config


def build_runtime_config(overrides: Optional[Dict[str, Any]] = None) -> RuntimeLLMConfig:
    """
    Формирует итоговую конфигурацию с учётом environment и module-config.
    
    Провайдер определяется через:
    1. Параметр overrides['provider']
    2. Переменную окружения LLM_PROVIDER (ollama|llama_cpp)
    3. По умолчанию - ollama
    """
    base_config = RuntimeLLMConfig()
    config = base_config.copy_with_overrides(overrides)
    config = _inject_env_defaults(config)

    # Если провайдер не был установлен явно, используем ollama по умолчанию
    if config.provider == LLMProvider.AUTO:
        config.provider = LLMProvider.OLLAMA
    
    return config


