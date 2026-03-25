"""
Автообнаружение каталогов прав модулей.

Сканирует все обнаруженные приложения и собирает PERMISSION_CATALOG
из файлов permission_catalog.py каждого модуля. Результат кешируется
в памяти процесса.
"""
import importlib
import logging
from typing import Dict, List, Optional

logger = logging.getLogger('utils')

_catalog_cache: Optional[Dict] = None


def _load_catalogs() -> Dict:
    from src.core.utils.auto_api.discovered_apps_cache import get_discovered_apps

    catalogs = {}
    all_keys = {}
    key_to_module = {}

    for app_path in get_discovered_apps():
        catalog_module_path = f'{app_path}.permission_catalog'
        try:
            mod = importlib.import_module(catalog_module_path)
        except ImportError:
            continue
        except Exception:
            logger.warning(
                'Ошибка при загрузке permission_catalog из %s',
                catalog_module_path,
                exc_info=True,
            )
            continue

        catalog = getattr(mod, 'PERMISSION_CATALOG', None)
        if not catalog or not isinstance(catalog, dict):
            continue

        module_name = catalog.get('module_name')
        permissions = catalog.get('permissions')
        if not module_name or not isinstance(permissions, dict):
            continue

        catalogs[module_name] = catalog
        all_keys.update(permissions)

        for perm_key in permissions:
            key_to_module[perm_key] = module_name

    return {
        'catalogs': catalogs,
        'all_keys': all_keys,
        'key_to_module': key_to_module,
    }


def _get_cache() -> Dict:
    global _catalog_cache
    if _catalog_cache is None:
        _catalog_cache = _load_catalogs()
    return _catalog_cache


def get_all_permission_keys() -> Dict[str, str]:
    """Единый словарь {permission_key: human_readable_name} по всем модулям."""
    return dict(_get_cache()['all_keys'])


def get_module_names() -> List[str]:
    """Список имён модулей, у которых есть каталог прав."""
    return list(_get_cache()['catalogs'].keys())


def resolve_module_name(permission_key: str) -> Optional[str]:
    """Определяет имя модуля по ключу права без хардкода."""
    return _get_cache()['key_to_module'].get(permission_key)


def get_module_permission_keys(module_name: str) -> Dict[str, str]:
    """Словарь прав конкретного модуля."""
    catalog = _get_cache()['catalogs'].get(module_name)
    if not catalog:
        return {}
    return dict(catalog.get('permissions', {}))


def clear_cache() -> None:
    """Сбрасывает кеш (например, при горячей перезагрузке)."""
    global _catalog_cache
    _catalog_cache = None
