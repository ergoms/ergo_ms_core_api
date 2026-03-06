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
        num_predict: Optional[int] = None,
        temperature: float,
        stream: bool = False,
        stream_callback: Optional[Callable[[str], None]] = None,
    ) -> str:
        raise NotImplementedError
    
    def chat(
        self,
        messages: List[Dict[str, str]],
        *,
        num_predict: Optional[int] = None,
        temperature: Optional[float] = None,
        seed: Optional[int] = None,
        stream: bool = False,
        stream_callback: Optional[Callable[[str], None]] = None,
        format: Optional[Any] = None,
    ) -> str:
        """
        Отправка сообщений в чат с сохранением контекста.

        Args:
            messages: Список сообщений [{"role": "user", "content": "..."}, ...]
            format: Ollama structured output — "json" или JSON-схема (опционально)
        """
        raise NotImplementedError

    def check_health(self) -> Dict[str, Any]:
        """Проверка доступности сервиса. Переопределяется в наследниках."""
        return {"available": False, "error": "Метод не реализован"}

    def get_provider_name(self) -> str:
        """Возвращает имя провайдера."""
        return "unknown"


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
        num_predict: Optional[int] = None,
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
    
    def chat(
        self,
        messages: List[Dict[str, str]],
        *,
        num_predict: Optional[int] = None,
        temperature: Optional[float] = None,
        seed: Optional[int] = None,
        stream: bool = False,
        stream_callback: Optional[Callable[[str], None]] = None,
        format: Optional[Any] = None,
    ) -> str:
        client = self._clients[0]
        return client.chat(
            messages,
            num_predict=num_predict,
            temperature=temperature,
            seed=seed,
            stream=stream,
            stream_callback=stream_callback,
            format=format,
        )

    def check_health(self) -> Dict[str, Any]:
        """Делегирует проверку первому клиенту."""
        if self._clients:
            return self._clients[0].check_health()
        return {"available": False, "error": "Нет клиентов"}

    def get_provider_name(self) -> str:
        """Возвращает имя провайдера первого клиента."""
        if self._clients:
            return self._clients[0].get_provider_name()
        return "unknown"


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
        # Для streaming запросов используем stream_timeout, для обычных - request_timeout
        # read timeout должен быть достаточно большим для streaming
        timeout = httpx.Timeout(
            timeout=request_timeout,
            connect=min(10.0, request_timeout),
            write=request_timeout,
            read=max(stream_timeout, request_timeout * 2),  # Увеличиваем для streaming
        )
        self._client = httpx.Client(base_url=self._base_url, timeout=timeout, limits=limits)
        self._keep_alive = keep_alive

    def get_provider_name(self) -> str:
        """Возвращает имя провайдера."""
        return "ollama"

    def check_health(self) -> Dict[str, Any]:
        """
        Быстрая проверка доступности Ollama без загрузки модели.
        Возвращает информацию о сервере и списке моделей.
        """
        try:
            # GET /api/tags - быстрая проверка без загрузки модели
            resp = self._client.get("/api/tags", timeout=5.0)
            resp.raise_for_status()
            data = resp.json()
            models = [m.get("name", "") for m in data.get("models", [])]
            return {
                "available": True,
                "models": models,
                "model_loaded": self.model in models or any(self.model in m for m in models),
            }
        except httpx.TimeoutException:
            return {"available": False, "error": "Таймаут подключения к Ollama"}
        except httpx.ConnectError:
            return {"available": False, "error": "Не удалось подключиться к Ollama"}
        except Exception as e:
            return {"available": False, "error": str(e)}

    def _build_payload(
        self,
        prompt: str,
        *,
        num_predict: Optional[int] = None,
        temperature: float,
        stream: bool,
    ) -> Dict[str, Any]:
        payload = {
            "model": self.model,
            "prompt": prompt,
            "stream": stream,
            "keep_alive": self._keep_alive,
            "options": {
                "temperature": temperature,
                "top_k": 40,
                "top_p": 0.9,
            },
        }
        if num_predict is not None:
            payload["options"]["num_predict"] = num_predict
        if self._device_config:
            payload["options"].update(self._device_config)
        return payload

    def complete(  # noqa: D401 - описание наследуется
        self,
        prompt: str,
        *,
        num_predict: Optional[int] = None,
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
        try:
            response = self._client.post("/api/generate", json=payload)
            response.raise_for_status()
            data = response.json()
            return data.get("response", "")
        except httpx.HTTPStatusError as e:
            if e.response.status_code == 404:
                error_msg = f"Ollama API вернул 404. Проверьте:\n"
                error_msg += f"1. URL: {self._base_url}/api/generate\n"
                error_msg += f"2. Модель '{self.model}' существует? Выполните: ollama list\n"
                error_msg += f"3. Если модели нет, установите: ollama pull {self.model}\n"
                error_msg += f"Ответ сервера: {e.response.text}"
                raise LLMClientError(error_msg) from e
            raise

    def _stream(
        self,
        payload: Dict[str, Any],
        stream_callback: Optional[Callable[[str], None]],
    ) -> str:
        chunks: List[str] = []
        try:
            with self._client.stream("POST", "/api/generate", json=payload) as response:
                # Для streaming response сначала проверяем статус
                # Если статус не 200, raise_for_status выбросит исключение
                try:
                    response.raise_for_status()
                except httpx.HTTPStatusError as status_error:
                    # Если ошибка 404, читаем содержимое для получения деталей
                    if status_error.response.status_code == 404:
                        try:
                            error_text = status_error.response.text
                        except Exception:
                            error_text = "Не удалось получить ответ сервера"
                        error_msg = f"Ollama API вернул 404. Проверьте:\n"
                        error_msg += f"1. URL: {self._base_url}/api/generate\n"
                        error_msg += f"2. Модель '{self.model}' существует? Выполните: ollama list\n"
                        error_msg += f"3. Если модели нет, установите: ollama pull {self.model}\n"
                        error_msg += f"Ответ сервера: {error_text}"
                        raise LLMClientError(error_msg) from status_error
                    raise
                
                # Читаем streaming данные построчно
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
        except LLMClientError:
            # Пробрасываем наши ошибки как есть
            raise
        except httpx.HTTPStatusError as e:
            # Обработка других HTTP ошибок
            if e.response.status_code == 404:
                try:
                    error_text = e.response.text
                except Exception:
                    error_text = "Не удалось получить ответ сервера"
                error_msg = f"Ollama API вернул 404. Проверьте:\n"
                error_msg += f"1. URL: {self._base_url}/api/generate\n"
                error_msg += f"2. Модель '{self.model}' существует? Выполните: ollama list\n"
                error_msg += f"3. Если модели нет, установите: ollama pull {self.model}\n"
                error_msg += f"Ответ сервера: {error_text}"
                raise LLMClientError(error_msg) from e
            raise
        return "".join(chunks)
    
    def chat(
        self,
        messages: List[Dict[str, str]],
        *,
        num_predict: Optional[int] = None,
        temperature: Optional[float] = None,
        seed: Optional[int] = None,
        stream: bool = False,
        stream_callback: Optional[Callable[[str], None]] = None,
        format: Optional[Any] = None,
    ) -> str:
        """
        Отправка сообщений в чат с сохранением контекста через /api/chat.
        format: Ollama structured output — "json" или JSON-схема (опционально).
        """
        payload = {
            "model": self.model,
            "messages": messages,
            "stream": stream,
            "keep_alive": self._keep_alive,
            "options": {
                "top_k": 40,
                "top_p": 0.9,
            },
        }
        if format is not None:
            payload["format"] = format
        if num_predict is not None:
            payload["options"]["num_predict"] = num_predict
        if temperature is not None:
            payload["options"]["temperature"] = temperature
        if seed is not None:
            payload["options"]["seed"] = seed
        if self._device_config:
            payload["options"].update(self._device_config)
        
        last_error: Optional[Exception] = None
        for attempt in range(self._max_retries + 1):
            try:
                if stream:
                    return self._stream_chat(payload, stream_callback)
                return self._chat(payload)
            except (httpx.TimeoutException, httpx.TransportError) as exc:
                last_error = exc
                logger.warning(
                    "Ошибка Ollama chat (попытка %s/%s): %s",
                    attempt + 1,
                    self._max_retries + 1,
                    exc,
                )
                continue
        raise LLMClientError("Ollama API недоступен") from last_error
    
    def _chat(self, payload: Dict[str, Any]) -> str:
        """Выполняет обычный (не streaming) запрос к /api/chat."""
        try:
            response = self._client.post("/api/chat", json=payload)
            response.raise_for_status()
            data = response.json()
            return data.get("message", {}).get("content", "")
        except httpx.HTTPStatusError as e:
            if e.response.status_code == 404:
                error_msg = f"Ollama API вернул 404. Проверьте:\n"
                error_msg += f"1. URL: {self._base_url}/api/chat\n"
                error_msg += f"2. Модель '{self.model}' существует? Выполните: ollama list\n"
                error_msg += f"3. Если модели нет, установите: ollama pull {self.model}\n"
                error_msg += f"Ответ сервера: {e.response.text}"
                raise LLMClientError(error_msg) from e
            raise
    
    def _stream_chat(
        self,
        payload: Dict[str, Any],
        stream_callback: Optional[Callable[[str], None]],
    ) -> str:
        """Выполняет streaming запрос к /api/chat."""
        chunks: List[str] = []
        try:
            with self._client.stream("POST", "/api/chat", json=payload) as response:
                try:
                    response.raise_for_status()
                except httpx.HTTPStatusError as status_error:
                    if status_error.response.status_code == 404:
                        try:
                            error_text = status_error.response.text
                        except Exception:
                            error_text = "Не удалось получить ответ сервера"
                        error_msg = f"Ollama API вернул 404. Проверьте:\n"
                        error_msg += f"1. URL: {self._base_url}/api/chat\n"
                        error_msg += f"2. Модель '{self.model}' существует? Выполните: ollama list\n"
                        error_msg += f"3. Если модели нет, установите: ollama pull {self.model}\n"
                        error_msg += f"Ответ сервера: {error_text}"
                        raise LLMClientError(error_msg) from status_error
                    raise
                
                for raw_line in response.iter_lines():
                    if not raw_line:
                        continue
                    try:
                        data = json.loads(raw_line)
                    except json.JSONDecodeError:
                        continue

                    message = data.get("message", {})
                    text = message.get("content") if isinstance(message, dict) else None
                    if text:
                        chunks.append(text)
                        if stream_callback:
                            stream_callback(text)
                    if data.get("done"):
                        break
        except LLMClientError:
            raise
        except httpx.HTTPStatusError as e:
            if e.response.status_code == 404:
                try:
                    error_text = e.response.text
                except Exception:
                    error_text = "Не удалось получить ответ сервера"
                error_msg = f"Ollama API вернул 404. Проверьте:\n"
                error_msg += f"1. URL: {self._base_url}/api/chat\n"
                error_msg += f"2. Модель '{self.model}' существует? Выполните: ollama list\n"
                error_msg += f"3. Если модели нет, установите: ollama pull {self.model}\n"
                error_msg += f"Ответ сервера: {error_text}"
                raise LLMClientError(error_msg) from e
            raise
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
    keep_alive: str = "10m",
    provider_config: Optional[Dict[str, Any]] = None,
    device_config: Optional[Dict[str, Any]] = None,
) -> BaseLLMClient:
    """Фабрика LLM клиентов с поддержкой Ollama."""
    provider_config = provider_config or {}
    device_config = device_config or {}

    normalized_provider = (provider or "ollama").lower()
    if normalized_provider == "llama_cpp":
        raise LLMClientError(
            "llama.cpp удалён. Используйте LLM_PROVIDER=ollama и Ollama для работы с LLM."
        )
    base_api_url = provider_config.get("base_url", base_url)

    if normalized_provider in ("auto", "ollama"):
        # Ollama клиент (по умолчанию)
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
    
    raise LLMClientError(f"Неподдерживаемый провайдер LLM: {provider}")
