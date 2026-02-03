from .config import build_runtime_config
from .llm_clients import build_llm_client
from .fast_bi_service import DEFAULT_MODEL, OLLAMA_BASE_URL


OLLAMA_OPTION_KEYS = ("top_p", "top_k", "repeat_penalty")


def create_ollama_client(ollama_config=None):
    config_with_defaults = ollama_config or {}
    if 'provider' not in config_with_defaults:
        config_with_defaults = {**config_with_defaults, 'provider': 'ollama'}
    if 'num_gpu' in config_with_defaults:
        if 'device_config' not in config_with_defaults:
            config_with_defaults['device_config'] = {}
        config_with_defaults['device_config']['num_gpu'] = config_with_defaults['num_gpu']
    runtime_config = build_runtime_config(config_with_defaults)
    for key in OLLAMA_OPTION_KEYS:
        if key in runtime_config.provider_config:
            runtime_config.device_config[key] = runtime_config.provider_config[key]
    provider_name = runtime_config.provider.value if hasattr(runtime_config.provider, "value") else str(runtime_config.provider)
    base_url = runtime_config.provider_config.get("base_url", runtime_config.base_url or OLLAMA_BASE_URL)
    client = build_llm_client(
        provider=provider_name,
        model=runtime_config.model or DEFAULT_MODEL,
        base_url=base_url,
        request_timeout=runtime_config.request_timeout,
        stream_timeout=runtime_config.stream_timeout,
        concurrency_limit=runtime_config.concurrency_limit,
        max_retries=runtime_config.max_retries,
        keep_alive=runtime_config.keep_alive,
        provider_config=runtime_config.provider_config,
        device_config=runtime_config.device_config,
    )
    return runtime_config, client
