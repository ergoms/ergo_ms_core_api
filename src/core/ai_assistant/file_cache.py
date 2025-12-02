# -*- coding: utf-8 -*-
"""
Модуль кеширования загруженных файлов для AI Assistant.
Кеширует Polars DataFrame и метаданные для избежания повторной загрузки.

Ключ кеша: (file_path, file_mtime)
TTL: 10 минут
Максимум записей: 50 (для ограничения памяти)
"""
import logging
import os
import time
import threading
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Optional, Tuple

import polars as pl

logger = logging.getLogger(__name__)

# Настройки кеша
CACHE_TTL_SECONDS = 600  # 10 минут
CACHE_MAX_SIZE = 50  # Максимум файлов в кеше


@dataclass
class CachedFile:
    """Закешированный файл с метаданными."""
    df: pl.DataFrame
    meta: Dict[str, Any]
    table_name: str
    created_at: float
    file_mtime: float
    access_count: int = 0
    last_access: float = 0


class FileCache:
    """
    LRU-кеш для загруженных файлов с TTL.
    
    Потокобезопасный, с автоматической очисткой устаревших записей.
    """
    
    def __init__(self, max_size: int = CACHE_MAX_SIZE, ttl: int = CACHE_TTL_SECONDS):
        self._cache: Dict[Tuple[str, float], CachedFile] = {}
        self._lock = threading.RLock()
        self._max_size = max_size
        self._ttl = ttl
        
        # Статистика
        self._hits = 0
        self._misses = 0
    
    def _get_cache_key(self, file_path: str) -> Optional[Tuple[str, float]]:
        """Создает ключ кеша из пути файла и времени модификации."""
        try:
            path = Path(file_path)
            if not path.exists():
                return None
            mtime = path.stat().st_mtime
            return (str(path.absolute()), mtime)
        except OSError:
            return None
    
    def get(self, file_path: str) -> Optional[CachedFile]:
        """
        Получает файл из кеша, если он есть и не устарел.
        
        Returns:
            CachedFile или None если не найден/устарел
        """
        cache_key = self._get_cache_key(file_path)
        if cache_key is None:
            return None
        
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
                logger.debug(f"Кеш истёк для файла: {file_path}")
                return None
            
            # Обновляем статистику доступа
            cached.access_count += 1
            cached.last_access = now
            self._hits += 1
            
            logger.debug(
                f"Кеш HIT для файла: {file_path} "
                f"(обращений: {cached.access_count}, "
                f"возраст: {now - cached.created_at:.1f}s)"
            )
            return cached
    
    def put(
        self,
        file_path: str,
        df: pl.DataFrame,
        meta: Dict[str, Any],
        table_name: str
    ) -> bool:
        """
        Добавляет файл в кеш.
        
        Returns:
            True если успешно добавлен
        """
        cache_key = self._get_cache_key(file_path)
        if cache_key is None:
            return False
        
        with self._lock:
            # Очищаем старые записи если кеш переполнен
            if len(self._cache) >= self._max_size:
                self._evict_oldest()
            
            now = time.time()
            self._cache[cache_key] = CachedFile(
                df=df,
                meta=meta,
                table_name=table_name,
                created_at=now,
                file_mtime=cache_key[1],
                access_count=0,
                last_access=now
            )
            
            logger.debug(
                f"Файл добавлен в кеш: {file_path} "
                f"(размер кеша: {len(self._cache)})"
            )
            return True
    
    def _evict_oldest(self) -> None:
        """Удаляет самые старые/редко используемые записи."""
        if not self._cache:
            return
        
        # Сортируем по last_access, удаляем 20% самых старых
        items = list(self._cache.items())
        items.sort(key=lambda x: x[1].last_access)
        
        to_remove = max(1, len(items) // 5)
        for i in range(to_remove):
            key = items[i][0]
            del self._cache[key]
            logger.debug(f"Удален из кеша (eviction): {key[0]}")
    
    def invalidate(self, file_path: str) -> bool:
        """
        Инвалидирует кеш для конкретного файла.
        
        Returns:
            True если запись была найдена и удалена
        """
        with self._lock:
            # Ищем все записи с этим путём (любой mtime)
            path_str = str(Path(file_path).absolute())
            keys_to_remove = [
                key for key in self._cache.keys()
                if key[0] == path_str
            ]
            
            for key in keys_to_remove:
                del self._cache[key]
                logger.debug(f"Кеш инвалидирован для: {file_path}")
            
            return bool(keys_to_remove)
    
    def clear(self) -> int:
        """
        Полностью очищает кеш.
        
        Returns:
            Количество удалённых записей
        """
        with self._lock:
            count = len(self._cache)
            self._cache.clear()
            logger.info(f"Кеш очищен, удалено записей: {count}")
            return count
    
    def cleanup_expired(self) -> int:
        """
        Удаляет все устаревшие записи.
        
        Returns:
            Количество удалённых записей
        """
        now = time.time()
        with self._lock:
            expired_keys = [
                key for key, cached in self._cache.items()
                if now - cached.created_at > self._ttl
            ]
            
            for key in expired_keys:
                del self._cache[key]
            
            if expired_keys:
                logger.debug(f"Удалено устаревших записей: {len(expired_keys)}")
            
            return len(expired_keys)
    
    def get_stats(self) -> Dict[str, Any]:
        """Возвращает статистику кеша."""
        with self._lock:
            total_requests = self._hits + self._misses
            hit_rate = (self._hits / total_requests * 100) if total_requests > 0 else 0
            
            # Подсчёт памяти (приблизительно)
            total_rows = sum(len(c.df) for c in self._cache.values())
            
            return {
                "entries": len(self._cache),
                "max_size": self._max_size,
                "hits": self._hits,
                "misses": self._misses,
                "hit_rate": round(hit_rate, 1),
                "ttl_seconds": self._ttl,
                "total_rows_cached": total_rows,
            }


# Глобальный экземпляр кеша (singleton)
_file_cache: Optional[FileCache] = None
_cache_lock = threading.Lock()


def get_file_cache() -> FileCache:
    """Возвращает глобальный экземпляр кеша файлов."""
    global _file_cache
    if _file_cache is None:
        with _cache_lock:
            if _file_cache is None:
                _file_cache = FileCache()
                logger.info(
                    f"Инициализирован кеш файлов: "
                    f"max_size={CACHE_MAX_SIZE}, ttl={CACHE_TTL_SECONDS}s"
                )
    return _file_cache


