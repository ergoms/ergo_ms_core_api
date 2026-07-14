"""
Прогрев соединений PostgreSQL и cache (Redis) при старте процесса API.

Первый HTTP-запрос после «Listening» у daphne не должен ждать cold connect к БД и кэшу.
"""

from __future__ import annotations

import logging
import os

logger = logging.getLogger(__name__)

WARMUP_CACHE_KEY = '__ergo_runtime_warmup__'


def _is_warmup_settings() -> bool:
    return os.environ.get('DJANGO_SETTINGS_MODULE', '') == 'src.config.patterns.warmup'


def warmup_runtime_connections() -> None:
    """Устанавливает соединение с БД и проверяет cache backend; ошибки не прерывают старт."""
    if _is_warmup_settings():
        return

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

        cache.set(WARMUP_CACHE_KEY, 1, timeout=1)
        cache.get(WARMUP_CACHE_KEY)
    except Exception as exc:
        logger.warning('[WARNING] Прогрев cache/Redis не удался: %s', exc)
