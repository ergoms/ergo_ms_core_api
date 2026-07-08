"""
Реестр модулей: список установленных модулей и флаг отключения.

Единая точка чтения DISABLED_MODULES из переменной окружения.
Используется в discovery приложений, URL, Celery и т.д.
"""

import os
from typing import FrozenSet, List


_cached_disabled: FrozenSet[str] | None = None


def get_disabled_modules() -> FrozenSet[str]:
    """
    Возвращает множество имён отключённых модулей.

    Читает DISABLED_MODULES из переменной окружения (через запятую).
    Результат кэшируется в рамках процесса.
    """
    global _cached_disabled
    if _cached_disabled is not None:
        return _cached_disabled

    raw = os.environ.get('DISABLED_MODULES', '')
    _cached_disabled = frozenset(
        m.strip() for m in raw.split(',') if m.strip()
    )
    return _cached_disabled


def is_module_disabled(module_name: str) -> bool:
    """Проверяет, отключён ли модуль по имени."""
    return module_name in get_disabled_modules()


_SKIPPED_MODULE_DIR_NAMES = frozenset({
    '__pycache__',
})


def is_valid_module_dir_name(name: str) -> bool:
    """Папка верхнего уровня modules/ — модуль, а не служебный каталог."""
    if not name or name.startswith('.'):
        return False
    return name not in _SKIPPED_MODULE_DIR_NAMES


def get_installed_module_names(*, include_disabled: bool = False) -> List[str]:
    """
    Имена модулей из каталога modules/ (любая подпапка верхнего уровня).

    Не импортирует приложения — только обход файловой системы.
    """
    from src.config.settings.base import MODULES_DIR

    disabled = get_disabled_modules()
    if not MODULES_DIR.exists() or not MODULES_DIR.is_dir():
        return []

    names: List[str] = []
    for entry in MODULES_DIR.iterdir():
        if not entry.is_dir() or not is_valid_module_dir_name(entry.name):
            continue
        if not include_disabled and entry.name in disabled:
            continue
        names.append(entry.name)

    return sorted(names)


def reset_cache() -> None:
    """Сбрасывает кэш (для тестов или при hot-reload)."""
    global _cached_disabled
    _cached_disabled = None
