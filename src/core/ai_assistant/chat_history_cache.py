# -*- coding: utf-8 -*-
"""
Модуль кеширования истории чата для AI Assistant.
Кеширует последние сообщения сессии для избежания повторных запросов к БД.

Ключ кеша: session_id
TTL: 5 минут (история может обновляться)
Максимум записей: 500 сессий
"""
import logging
import threading
import time
from dataclasses import dataclass
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

# Настройки кеша
CACHE_TTL_SECONDS = 300  # 5 минут
CACHE_MAX_SIZE = 500  # Максимум сессий в кеше


@dataclass
class CachedHistory:
    """Закешированная история чата."""
    messages: List[Dict[str, Any]]
    created_at: float
    last_access: float
    access_count: int = 0


class ChatHistoryCache:
    """
    LRU-кеш для истории чата с TTL.
    
    Потокобезопасный, с автоматической очисткой устаревших записей.
    """
    
    def __init__(self, max_size: int = CACHE_MAX_SIZE, ttl: int = CACHE_TTL_SECONDS):
        self._cache: Dict[str, CachedHistory] = {}
        self._lock = threading.RLock()
        self._max_size = max_size
        self._ttl = ttl
        
        # Статистика
        self._hits = 0
        self._misses = 0
    
    def get(self, session_id: str) -> Optional[List[Dict[str, Any]]]:
        """
        Получает историю из кеша, если она есть и не устарела.
        
        Returns:
            Список сообщений или None если не найден/устарел
        """
        with self._lock:
            cached = self._cache.get(session_id)
            if cached is None:
                self._misses += 1
                return None
            
            # Проверяем TTL
            now = time.time()
            if now - cached.created_at > self._ttl:
                # Запись устарела, удаляем
                del self._cache[session_id]
                self._misses += 1
                logger.debug(f"Кеш истёк для сессии: {session_id}")
                return None
            
            # Обновляем статистику доступа
            cached.access_count += 1
            cached.last_access = now
            self._hits += 1
            
            logger.debug(
                f"Кеш HIT для сессии: {session_id} "
                f"(обращений: {cached.access_count}, "
                f"возраст: {now - cached.created_at:.1f}s)"
            )
            return cached.messages.copy()  # Возвращаем копию
    
    def put(self, session_id: str, messages: List[Dict[str, Any]]) -> bool:
        """
        Сохраняет историю в кеш.
        
        Returns:
            True если успешно сохранено, False если кеш переполнен
        """
        now = time.time()
        
        with self._lock:
            # Если кеш переполнен, удаляем самые старые записи
            if len(self._cache) >= self._max_size:
                self._evict_oldest()
            
            # Сохраняем историю
            self._cache[session_id] = CachedHistory(
                messages=messages.copy(),  # Сохраняем копию
                created_at=now,
                last_access=now,
                access_count=1,
            )
            
            logger.debug(f"История закеширована для сессии: {session_id}")
            return True
    
    def invalidate(self, session_id: str) -> None:
        """Удаляет историю сессии из кеша (при добавлении нового сообщения)."""
        with self._lock:
            if session_id in self._cache:
                del self._cache[session_id]
                logger.debug(f"История удалена из кеша для сессии: {session_id}")
    
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
        for session_id, _ in sorted_items[:evict_count]:
            del self._cache[session_id]
        
        logger.debug(f"Удалено {evict_count} старых записей из кеша истории")
    
    def clear(self) -> None:
        """Очищает весь кеш."""
        with self._lock:
            self._cache.clear()
            self._hits = 0
            self._misses = 0
            logger.info("Кеш истории чата очищен")
    
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
_history_cache: Optional[ChatHistoryCache] = None
_cache_lock = threading.Lock()


def get_chat_history_cache() -> ChatHistoryCache:
    """Возвращает глобальный экземпляр кеша истории чата."""
    global _history_cache
    if _history_cache is None:
        with _cache_lock:
            if _history_cache is None:
                _history_cache = ChatHistoryCache()
                logger.info(
                    f"Инициализирован кеш истории чата: "
                    f"max_size={CACHE_MAX_SIZE}, ttl={CACHE_TTL_SECONDS}s"
                )
    return _history_cache


