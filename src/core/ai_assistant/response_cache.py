# -*- coding: utf-8 -*-
"""
Модуль кеширования ответов LLM для AI Assistant.
Кеширует ответы для похожих вопросов, чтобы избежать повторных запросов к LLM.

Ключ кеша: hash(prompt + model + temperature)
TTL: 1 час (для стабильных ответов)
Максимум записей: 1000 (для ограничения памяти)
"""
import hashlib
import logging
import threading
import time
from dataclasses import dataclass
from typing import Any, Dict, Optional, Tuple

logger = logging.getLogger(__name__)

# Настройки кеша
CACHE_TTL_SECONDS = 3600  # 1 час
CACHE_MAX_SIZE = 1000  # Максимум ответов в кеше


@dataclass
class CachedResponse:
    """Закешированный ответ LLM."""
    response: str
    created_at: float
    access_count: int = 0
    last_access: float = 0
    prompt_hash: str = ""


class ResponseCache:
    """
    LRU-кеш для ответов LLM с TTL.
    
    Потокобезопасный, с автоматической очисткой устаревших записей.
    """
    
    def __init__(self, max_size: int = CACHE_MAX_SIZE, ttl: int = CACHE_TTL_SECONDS):
        self._cache: Dict[str, CachedResponse] = {}
        self._lock = threading.RLock()
        self._max_size = max_size
        self._ttl = ttl
        
        # Статистика
        self._hits = 0
        self._misses = 0
    
    def _get_cache_key(self, prompt: str, model: str, temperature: float, num_predict: int) -> str:
        """Создает ключ кеша из промпта, модели и параметров."""
        # Нормализуем промпт (убираем лишние пробелы)
        normalized_prompt = " ".join(prompt.split())
        
        # Создаем хеш из промпта, модели и параметров
        cache_string = f"{normalized_prompt}|{model}|{temperature}|{num_predict}"
        return hashlib.sha256(cache_string.encode('utf-8')).hexdigest()
    
    def get(
        self,
        prompt: str,
        model: str,
        temperature: float,
        num_predict: int
    ) -> Optional[str]:
        """
        Получает ответ из кеша, если он есть и не устарел.
        
        Returns:
            Ответ или None если не найден/устарел
        """
        cache_key = self._get_cache_key(prompt, model, temperature, num_predict)
        
        with self._lock:
            cached = self._cache.get(cache_key)
            if cached is None:
                self._misses += 1
                return None
            
            # Проверяем TTL
            now = time.time()
            if now - cached.created_at > self._ttl:
                # Запись устарела, удаляем
                del self._cache[cache_key]
                self._misses += 1
                logger.debug(f"Кеш истёк для промпта (hash: {cache_key[:16]}...)")
                return None
            
            # Обновляем статистику доступа
            cached.access_count += 1
            cached.last_access = now
            self._hits += 1
            
            logger.debug(
                f"Кеш HIT для промпта (hash: {cache_key[:16]}...) "
                f"(обращений: {cached.access_count}, "
                f"возраст: {now - cached.created_at:.1f}s)"
            )
            return cached.response
    
    def put(
        self,
        prompt: str,
        model: str,
        temperature: float,
        num_predict: int,
        response: str
    ) -> bool:
        """
        Сохраняет ответ в кеш.
        
        Returns:
            True если успешно сохранено, False если кеш переполнен
        """
        cache_key = self._get_cache_key(prompt, model, temperature, num_predict)
        now = time.time()
        
        with self._lock:
            # Если кеш переполнен, удаляем самые старые записи
            if len(self._cache) >= self._max_size:
                self._evict_oldest()
            
            # Сохраняем ответ
            self._cache[cache_key] = CachedResponse(
                response=response,
                created_at=now,
                last_access=now,
                access_count=1,
                prompt_hash=cache_key,
            )
            
            logger.debug(f"Ответ закеширован (hash: {cache_key[:16]}...)")
            return True
    
    def _evict_oldest(self) -> None:
        """Удаляет самые старые записи (LRU)."""
        if not self._cache:
            return
        
        # Сортируем по времени последнего доступа
        sorted_items = sorted(
            self._cache.items(),
            key=lambda x: x[1].last_access
        )
        
        # Удаляем 10% самых старых записей
        evict_count = max(1, len(sorted_items) // 10)
        for cache_key, _ in sorted_items[:evict_count]:
            del self._cache[cache_key]
        
        logger.debug(f"Удалено {evict_count} старых записей из кеша")
    
    def clear(self) -> None:
        """Очищает весь кеш."""
        with self._lock:
            self._cache.clear()
            self._hits = 0
            self._misses = 0
            logger.info("Кеш ответов очищен")
    
    def get_stats(self) -> Dict[str, Any]:
        """Возвращает статистику кеша."""
        with self._lock:
            total_requests = self._hits + self._misses
            hit_rate = (self._hits / total_requests * 100) if total_requests > 0 else 0
            
            return {
                'size': len(self._cache),
                'max_size': self._max_size,
                'hits': self._hits,
                'misses': self._misses,
                'hit_rate': round(hit_rate, 2),
                'ttl_seconds': self._ttl,
            }


# Глобальный экземпляр кеша (singleton)
_response_cache: Optional[ResponseCache] = None
_cache_lock = threading.Lock()


def get_response_cache() -> ResponseCache:
    """Возвращает глобальный экземпляр кеша ответов."""
    global _response_cache
    if _response_cache is None:
        with _cache_lock:
            if _response_cache is None:
                _response_cache = ResponseCache()
                logger.info(
                    f"Инициализирован кеш ответов LLM: "
                    f"max_size={CACHE_MAX_SIZE}, ttl={CACHE_TTL_SECONDS}s"
                )
    return _response_cache


