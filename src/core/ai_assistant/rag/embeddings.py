"""
Сервис для генерации embeddings через Ollama API
"""
import logging
from typing import List, Optional, Dict, Any
import httpx

logger = logging.getLogger(__name__)


class EmbeddingsError(Exception):
    """Общее исключение для ошибок работы с embeddings."""
    pass


class OllamaEmbeddingsService:
    """
    Сервис для генерации embeddings через Ollama API
    
    Использует endpoint /api/embed для генерации векторных представлений текста.
    Поддерживает как одиночные запросы, так и батч-обработку.
    """
    
    def __init__(
        self,
        base_url: str = "http://localhost:11434",
        model: str = "embeddinggemma",
        request_timeout: float = 30.0,
    ):
        """
        Инициализация сервиса embeddings
        
        Args:
            base_url: Базовый URL Ollama сервера
            model: Название модели для генерации embeddings
                   Рекомендуемые модели: embeddinggemma (по умолчанию), qwen3-embedding, all-minilm
                   Можно изменить через переменную окружения OLLAMA_EMBEDDINGS_MODEL
            request_timeout: Таймаут запроса в секундах
        """
        self._base_url = base_url.rstrip("/")
        self._model = model
        self._request_timeout = request_timeout
        self._client = httpx.Client(base_url=self._base_url, timeout=request_timeout)
    
    def generate_embedding(self, text: str) -> List[float]:
        """
        Генерирует embedding для одного текста
        
        Args:
            text: Текст для генерации embedding
            
        Returns:
            Список чисел (вектор embedding), L2-нормализованный
            
        Raises:
            EmbeddingsError: При ошибке генерации embedding
        """
        if not text or not text.strip():
            raise EmbeddingsError("Текст не может быть пустым")
        
        try:
            response = self._client.post(
                "/api/embed",
                json={
                    "model": self._model,
                    "input": text.strip()
                }
            )
            response.raise_for_status()
            data = response.json()
            
            # Ollama может вернуть как "embedding" (единственное число), так и "embeddings" (множественное)
            # Некоторые модели (например, embeddinggemma) всегда возвращают "embeddings" даже для одного текста
            embedding = None
            
            # Сначала проверяем единственное число
            if "embedding" in data:
                embedding = data["embedding"]
            # Затем проверяем множественное число
            elif "embeddings" in data:
                embeddings_list = data["embeddings"]
                if isinstance(embeddings_list, list):
                    if len(embeddings_list) > 0:
                        # Если это список списков (батч), берем первый
                        if isinstance(embeddings_list[0], list):
                            embedding = embeddings_list[0]
                        # Если это список чисел (один embedding), используем его
                        elif isinstance(embeddings_list[0], (int, float)):
                            embedding = embeddings_list
                elif isinstance(embeddings_list, (int, float)):
                    # Если это один number (не должно быть, но на всякий случай)
                    embedding = [embeddings_list]
            
            if embedding is None:
                raise EmbeddingsError(f"Ollama вернул ответ без embedding/embeddings. Ключи в ответе: {list(data.keys())}, Ответ: {data}")
            
            # Убеждаемся, что это список чисел
            if not isinstance(embedding, list) or not all(isinstance(x, (int, float)) for x in embedding):
                raise EmbeddingsError(f"Ollama вернул embedding неверного формата (ожидается список чисел): {type(embedding)}")
            
            return embedding
            
        except httpx.TimeoutException:
            raise EmbeddingsError(f"Таймаут при генерации embedding (>{self._request_timeout}s)")
        except httpx.ConnectError:
            raise EmbeddingsError(f"Не удалось подключиться к Ollama по адресу {self._base_url}")
        except httpx.HTTPStatusError as e:
            if e.response.status_code == 404:
                error_msg = (
                    f"Модель '{self._model}' не найдена. "
                    f"Установите модель командой: ollama pull {self._model}\n"
                    f"Рекомендуемые модели: embeddinggemma, qwen3-embedding, all-minilm\n"
                    f"Модель можно изменить через переменную окружения OLLAMA_EMBEDDINGS_MODEL"
                )
                raise EmbeddingsError(error_msg) from e
            raise EmbeddingsError(f"HTTP ошибка {e.response.status_code}: {e.response.text}") from e
        except Exception as e:
            raise EmbeddingsError(f"Неожиданная ошибка при генерации embedding: {e}") from e
    
    def generate_embeddings_batch(self, texts: List[str]) -> List[List[float]]:
        """
        Генерирует embeddings для списка текстов (батч-обработка)
        
        Args:
            texts: Список текстов для генерации embeddings
            
        Returns:
            Список векторов embeddings (каждый элемент - список float)
            
        Raises:
            EmbeddingsError: При ошибке генерации embeddings
        """
        if not texts:
            return []
        
        # Фильтруем пустые тексты
        valid_texts = [text.strip() for text in texts if text and text.strip()]
        if not valid_texts:
            raise EmbeddingsError("Нет валидных текстов для обработки")
        
        try:
            response = self._client.post(
                "/api/embed",
                json={
                    "model": self._model,
                    "input": valid_texts
                }
            )
            response.raise_for_status()
            data = response.json()
            
            # Ollama может вернуть как "embeddings" (множественное число), так и "embedding" (единственное)
            embeddings = data.get("embeddings")
            
            if not embeddings:
                # Проверяем единственное число (для одного текста)
                embedding = data.get("embedding")
                if embedding:
                    # Если вернулся один embedding, оборачиваем в список
                    embeddings = [embedding] if isinstance(embedding, list) else [[embedding]]
                else:
                    raise EmbeddingsError(f"Ollama вернул ответ без embeddings/embedding. Ответ: {data}")
            
            # Если embeddings - это список, но первый элемент не список (один embedding как плоский список)
            if isinstance(embeddings, list) and len(embeddings) > 0:
                # Проверяем, является ли первый элемент списком чисел
                if isinstance(embeddings[0], (int, float)):
                    # Это один embedding в виде плоского списка - оборачиваем в список
                    embeddings = [embeddings]
                elif isinstance(embeddings[0], list) and len(embeddings[0]) > 0 and isinstance(embeddings[0][0], (int, float)):
                    # Это правильный формат: список списков чисел
                    pass
                else:
                    raise EmbeddingsError(f"Неверный формат embeddings: {type(embeddings[0])}")
            else:
                raise EmbeddingsError(f"Ollama вернул embeddings неверного формата: {type(embeddings)}")
            
            # Проверяем, что количество embeddings совпадает с количеством текстов
            if len(embeddings) != len(valid_texts):
                logger.warning(
                    f"Количество embeddings ({len(embeddings)}) не совпадает с количеством текстов ({len(valid_texts)})"
                )
            
            return embeddings
            
        except httpx.TimeoutException:
            raise EmbeddingsError(f"Таймаут при генерации embeddings (>{self._request_timeout}s)")
        except httpx.ConnectError:
            raise EmbeddingsError(f"Не удалось подключиться к Ollama по адресу {self._base_url}")
        except httpx.HTTPStatusError as e:
            if e.response.status_code == 404:
                error_msg = (
                    f"Модель '{self._model}' не найдена. "
                    f"Установите модель командой: ollama pull {self._model}\n"
                    f"Рекомендуемые модели: embeddinggemma, qwen3-embedding, all-minilm\n"
                    f"Модель можно изменить через переменную окружения OLLAMA_EMBEDDINGS_MODEL"
                )
                raise EmbeddingsError(error_msg) from e
            raise EmbeddingsError(f"HTTP ошибка {e.response.status_code}: {e.response.text}") from e
        except Exception as e:
            raise EmbeddingsError(f"Неожиданная ошибка при генерации embeddings: {e}") from e
    
    def check_health(self) -> Dict[str, Any]:
        """
        Проверка доступности сервиса embeddings
        
        Returns:
            Словарь с информацией о статусе сервиса
        """
        try:
            # Проверяем доступность Ollama
            response = self._client.get("/api/tags", timeout=5.0)
            response.raise_for_status()
            data = response.json()
            models = [m.get("name", "") for m in data.get("models", [])]
            
            model_available = any(
                self._model in m or m.startswith(self._model)
                for m in models
            )
            
            return {
                "available": True,
                "model": self._model,
                "model_available": model_available,
                "base_url": self._base_url,
                "available_models": models,
            }
        except Exception as e:
            return {
                "available": False,
                "model": self._model,
                "error": str(e),
                "base_url": self._base_url,
            }
    
    def close(self):
        """Закрывает HTTP клиент"""
        if hasattr(self, "_client"):
            self._client.close()

