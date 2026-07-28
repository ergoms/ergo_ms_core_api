"""
Реестр модулей: список установленных модулей и флаг отключения.

Единая точка чтения DISABLED_MODULES. Реализация каталога — lifecycle.modules.catalog.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path
from typing import FrozenSet, List

from src.config.settings.base import MODULES_DIR, SYSTEM_DIR

_cached_catalog = None


def _deployment_dir() -> Path:
    return SYSTEM_DIR / 'core' / 'deployment'


def _get_catalog():
    global _cached_catalog
    if _cached_catalog is not None:
        return _cached_catalog

    deployment = _deployment_dir()
    if str(deployment) not in sys.path:
        sys.path.insert(0, str(deployment))

    from lifecycle.modules.catalog import ModuleCatalog  # noqa: WPS433

    _cached_catalog = ModuleCatalog.from_env(SYSTEM_DIR)
    return _cached_catalog


def get_disabled_modules() -> FrozenSet[str]:
    """Возвращает множество имён отключённых модулей (кэш процесса)."""
    return _get_catalog().disabled


def is_module_disabled(module_name: str) -> bool:
    """Проверяет, отключён ли модуль по имени."""
    return _get_catalog().is_disabled(module_name)


def is_valid_module_dir_name(name: str) -> bool:
    """Папка верхнего уровня modules/ — модуль, а не служебный каталог."""
    deployment = _deployment_dir()
    if str(deployment) not in sys.path:
        sys.path.insert(0, str(deployment))
    from lifecycle.modules.catalog import ModuleCatalog  # noqa: WPS433

    return ModuleCatalog.is_valid_module_dir_name(name)


def is_valid_module_name(module_name: str) -> bool:
    """
    Имя модуля для Celery/discovery: только a-z и `_`, без цифр и верхнего регистра.
    Без Django — используется при прогреве кэшей без django.setup().
    """
    return bool(re.match(r'^[a-z_]+$', module_name))


def get_installed_module_names(*, include_disabled: bool = False) -> List[str]:
    """
    Имена установленных модулей из ``modules/`` (есть ``api/`` и/или ``client/``).

    Пустые placeholder-каталоги (неинициализированные submodule) не включаются.
    Не импортирует приложения — только обход файловой системы.
    """
    if not MODULES_DIR.exists() or not MODULES_DIR.is_dir():
        return []
    return _get_catalog().list_module_names(include_disabled=include_disabled)


def reset_cache() -> None:
    """Сбрасывает кэш (для тестов или при hot-reload)."""
    global _cached_catalog
    _cached_catalog = None


def top_level_module_from_menu_source(module_source: str) -> str | None:
    """``modules/<name>/…`` → ``<name>``; иначе ``None``."""
    deployment = _deployment_dir()
    if str(deployment) not in sys.path:
        sys.path.insert(0, str(deployment))
    from lifecycle.modules.module_source import top_level_from_module_source  # noqa: WPS433

    return top_level_from_module_source(module_source)
