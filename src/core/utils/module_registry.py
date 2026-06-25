"""
Реестр модулей: определяет какие модули отключены.

Единая точка чтения DISABLED_MODULES из переменной окружения.
Используется в discovery приложений, URL, Celery и т.д.
"""

import os
from typing import FrozenSet


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


def reset_cache() -> None:
    """Сбрасывает кэш (для тестов или при hot-reload)."""
    global _cached_disabled
    _cached_disabled = None
