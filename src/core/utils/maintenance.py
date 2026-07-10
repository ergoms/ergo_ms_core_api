"""Проверка режима технических works по флаг-файлу в корне проекта."""

from pathlib import Path

from src.config.paths import SYSTEM_DIR

MAINTENANCE_FLAG_NAME = 'maintenance.flag'
MAINTENANCE_STATUS_PATH = '/api/system/maintenance-status/'
MAINTENANCE_DETAIL = 'Система временно недоступна. Мы проводим обновление и скоро вернёмся.'


def maintenance_flag_path() -> Path:
    return SYSTEM_DIR / MAINTENANCE_FLAG_NAME


def is_maintenance_enabled() -> bool:
    return maintenance_flag_path().is_file()


def is_maintenance_status_request(path: str) -> bool:
    normalized = path if path.endswith('/') else f'{path}/'
    return normalized == MAINTENANCE_STATUS_PATH
