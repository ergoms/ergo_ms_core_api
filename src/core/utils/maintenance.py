"""Проверка режима технических работ по флаг-файлу в корне проекта."""

import time
from pathlib import Path

from src.config.paths import SYSTEM_DIR

MAINTENANCE_FLAG_NAME = 'maintenance.flag'
MAINTENANCE_STATUS_PATH = '/api/system/maintenance-status/'
READY_PATH = '/api/system/ready/'
MAINTENANCE_DETAIL = 'Система временно недоступна. Мы проводим обновление и скоро вернёмся.'
_MAINTENANCE_EXEMPT_PATHS = frozenset({MAINTENANCE_STATUS_PATH, READY_PATH})


def maintenance_flag_path() -> Path:
    return SYSTEM_DIR / MAINTENANCE_FLAG_NAME


_FLAG_CACHE_SECONDS = 1.5
_cached_flag: bool | None = None
_cached_flag_at = 0.0


def is_maintenance_enabled() -> bool:
    """Флаг на диске, с короткой памятью: stat не на каждый запрос."""
    global _cached_flag, _cached_flag_at
    now = time.monotonic()
    if _cached_flag is not None and now - _cached_flag_at < _FLAG_CACHE_SECONDS:
        return _cached_flag
    _cached_flag = maintenance_flag_path().is_file()
    _cached_flag_at = now
    return _cached_flag


def is_maintenance_exempt_request(path: str) -> bool:
    """Статус обслуживания и healthcheck оркестрации остаются доступны."""
    normalized = path if path.endswith('/') else f'{path}/'
    return normalized in _MAINTENANCE_EXEMPT_PATHS
