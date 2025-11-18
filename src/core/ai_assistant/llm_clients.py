from __future__ import annotations

import json
import logging
from typing import Any, Callable, Dict, Iterable, List, Optional

import httpx

logger = logging.getLogger(__name__)


class LLMClientError(RuntimeError):
    """Общее исключение для ошибок работы с LLM провайдерами."""


class BaseLLMClient:
    """Базовый интерфейс LLM клиента."""

    def __init__(self, model: str) -> None:
        self.model = model

    def complete(
        self,
        prompt: str,
        *,
        num_predict: int,
        temperature: float,
        stream: bool = False,
        stream_callback: Optional[Callable[[str], None]] = None,
    ) -> str:
        raise NotImplementedError


class CompositeLLMClient(BaseLLMClient):
    """Клиент-обёртка, позволяющий использовать единый интерфейс LLM."""

    def __init__(self, model: str, clients: Iterable[BaseLLMClient]) -> None:
        super().__init__(model=model)
        self._clients: List[BaseLLMClient] = list(clients)
        if not self._clients:
            raise ValueError("Не передан ни один LLM провайдер")

    def complete(  # noqa: D401
        self,
        prompt: str,
        *,
        num_predict: int,
        temperature: float,
        stream: bool = False,
        stream_callback: Optional[Callable[[str], None]] = None,
    ) -> str:
        client = self._clients[0]
        return client.complete(
            prompt,
            num_predict=num_predict,
            temperature=temperature,
            stream=stream,
            stream_callback=stream_callback,
        )


class HttpxOllamaClient(BaseLLMClient):
    """Быстрый HTTP клиент для Ollama API."""

    def __init__(
        self,
        *,
        model: str,
        base_url: str,
        request_timeout: float,
        stream_timeout: float,
        concurrency_limit: int,
        max_retries: int,
        keep_alive: str,
        device_config: Optional[Dict[str, Any]] = None,
    ) -> None:
        super().__init__(model=model)
        self._base_url = base_url.rstrip("/")
        self._stream_timeout = stream_timeout
        self._max_retries = max_retries
        self._device_config = device_config or {}

        limits = httpx.Limits(
            max_connections=concurrency_limit,
            max_keepalive_connections=concurrency_limit,
        )
        timeout = httpx.Timeout(
            timeout=request_timeout,
            connect=min(10.0, request_timeout),
            write=request_timeout,
            read=max(stream_timeout, request_timeout),
        )
        self._client = httpx.Client(base_url=self._base_url, timeout=timeout, limits=limits)
        self._keep_alive = keep_alive

    def _build_payload(
        self,
        prompt: str,
        *,
        num_predict: int,
        temperature: float,
        stream: bool,
    ) -> Dict[str, Any]:
        payload = {
            "model": self.model,
            "prompt": prompt,
            "stream": stream,
            "keep_alive": self._keep_alive,
            "options": {
                "num_predict": num_predict,
                "temperature": temperature,
                "top_k": 40,
                "top_p": 0.9,
            },
        }
        if self._device_config:
            payload["options"].update(self._device_config)
        return payload

    def complete(  # noqa: D401 - описание наследуется
        self,
        prompt: str,
        *,
        num_predict: int,
        temperature: float,
        stream: bool = False,
        stream_callback: Optional[Callable[[str], None]] = None,
    ) -> str:
        payload = self._build_payload(
            prompt,
            num_predict=num_predict,
            temperature=temperature,
            stream=stream,
        )

        last_error: Optional[Exception] = None
        for attempt in range(self._max_retries + 1):
            try:
                if stream:
                    return self._stream(payload, stream_callback)
                return self._complete(payload)
            except (httpx.TimeoutException, httpx.TransportError) as exc:
                last_error = exc
                logger.warning(
                    "Ошибка Ollama (попытка %s/%s): %s",
                    attempt + 1,
                    self._max_retries + 1,
                    exc,
                )
                continue
        raise LLMClientError("Ollama API недоступен") from last_error

    def _complete(self, payload: Dict[str, Any]) -> str:
        response = self._client.post("/api/generate", json=payload)
        response.raise_for_status()
        data = response.json()
        return data.get("response", "")

    def _stream(
        self,
        payload: Dict[str, Any],
        stream_callback: Optional[Callable[[str], None]],
    ) -> str:
        chunks: List[str] = []
        with self._client.stream("POST", "/api/generate", json=payload) as response:
            response.raise_for_status()
            for raw_line in response.iter_lines():
                if not raw_line:
                    continue
                try:
                    data = json.loads(raw_line)
                except json.JSONDecodeError:
                    continue

                text = data.get("response")
                if text:
                    chunks.append(text)
                    if stream_callback:
                        stream_callback(text)
                if data.get("done"):
                    break
        return "".join(chunks)


def build_llm_client(
    *,
    provider: str,
    model: str,
    base_url: str,
    request_timeout: float,
    stream_timeout: float,
    concurrency_limit: int,
    max_retries: int,
    keep_alive: str,
    provider_config: Optional[Dict[str, Any]] = None,
    device_config: Optional[Dict[str, Any]] = None,
) -> BaseLLMClient:
    """Фабрика LLM клиентов с fallback."""
    provider_config = provider_config or {}
    device_config = device_config or {}

    normalized_provider = (provider or "ollama").lower()
    base_api_url = provider_config.get("base_url", base_url)

    if normalized_provider not in ("auto", "ollama"):
        raise LLMClientError(f"Неподдерживаемый провайдер LLM: {provider}")

    client = HttpxOllamaClient(
        model=model,
        base_url=base_api_url,
        request_timeout=request_timeout,
        stream_timeout=stream_timeout,
        concurrency_limit=concurrency_limit,
        max_retries=max_retries,
        keep_alive=keep_alive,
        device_config=device_config,
    )
    return CompositeLLMClient(model=model, clients=[client])
