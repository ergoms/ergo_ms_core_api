"""
Прогрев соединений PostgreSQL и cache (Redis) при старте процесса API.

Первый HTTP-запрос после «Listening» у daphne не должен ждать cold connect к БД и кэшу.
"""

from __future__ import annotations

import logging
import time

logger = logging.getLogger(__name__)

WARMUP_CACHE_KEY = '__ergo_runtime_warmup__'
_REDIS_WARMUP_ATTEMPTS = 5
_REDIS_WARMUP_DELAY_SEC = 0.5


def warmup_runtime_connections() -> None:
    """Устанавливает соединение с БД и проверяет cache backend; ошибки не прерывают старт."""
    try:
        from django.db import connections

        connection = connections['default']
        connection.ensure_connection()
        with connection.cursor() as cursor:
            cursor.execute('SELECT 1')
    except Exception as exc:
        logger.warning('[WARNING] Прогрев PostgreSQL не удался: %s', exc)

    try:
        from django.core.cache import cache
        from src.config.redis_runtime import effective_cache_backend

        attempts = _REDIS_WARMUP_ATTEMPTS if effective_cache_backend() == 'redis' else 1
        last_exc: Exception | None = None
        for attempt in range(attempts):
            try:
                cache.set(WARMUP_CACHE_KEY, 1, timeout=1)
                cache.get(WARMUP_CACHE_KEY)
                last_exc = None
                break
            except Exception as exc:
                last_exc = exc
                if attempt + 1 < attempts:
                    time.sleep(_REDIS_WARMUP_DELAY_SEC)
        if last_exc is not None:
            logger.warning('[WARNING] Прогрев cache/Redis не удался: %s', last_exc)
    except Exception as exc:
        logger.warning('[WARNING] Прогрев cache/Redis не удался: %s', exc)
