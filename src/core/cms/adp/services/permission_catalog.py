"""
Автообнаружение каталогов прав модулей.

Сканирует все обнаруженные приложения и собирает PERMISSION_CATALOG
из файлов permission_catalog.py каждого модуля. Результат кешируется
в памяти процесса.
"""
import importlib
import logging
from typing import Any, Dict, FrozenSet, List, Optional

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


def _format_module_slug(module_name: str) -> str:
    """Читаемая подпись из slug папки модуля."""
    return module_name.replace('-', ' ').replace('_', ' ').strip().title()


def _resolve_module_label(module_name: str, catalog: Optional[Dict] = None) -> str:
    """Человекочитаемое имя модуля: из каталога, AppConfig или slug."""
    if catalog:
        label = catalog.get('module_label')
        if isinstance(label, str) and label.strip():
            return label.strip()

    try:
        from django.apps import apps

        app_config = apps.get_app_config(module_name)
        verbose_name = getattr(app_config, 'verbose_name', None)
        if isinstance(verbose_name, str) and verbose_name.strip():
            return verbose_name.strip()
    except LookupError:
        pass

    return _format_module_slug(module_name)


def _merge_stored_module_permissions(modules: List[Dict[str, Any]], *, disabled: FrozenSet[str]) -> None:
    """Дополняет каталог ключами прав, уже сохранёнными в ModulePermission."""
    from src.core.cms.adp.models import ModulePermission

    by_name = {item['module_name']: item for item in modules}
    rows = (
        ModulePermission.objects
        .values('module_name', 'permission_key', 'permission_name')
        .order_by('module_name', 'permission_key')
        .distinct()
    )
    for row in rows:
        module_name = row['module_name']
        if module_name not in by_name:
            by_name[module_name] = {
                'module_name': module_name,
                'module_label': _format_module_slug(module_name),
                'has_permission_catalog': False,
                'permissions': {},
                'disabled': module_name in disabled,
            }
            modules.append(by_name[module_name])

        permissions = by_name[module_name]['permissions']
        key = row['permission_key']
        if key and key not in permissions:
            label = (row.get('permission_name') or '').strip()
            permissions[key] = label or key

    modules.sort(key=lambda item: item['module_name'])


def get_modules_catalog(*, include_disabled: bool = False) -> List[Dict[str, Any]]:
    """
    Централизованный каталог модулей для UI и ADP.

    Список — только установленные модули из ``modules/`` (есть ``api/``
    и/или ``client/``; пустые placeholder-папки не включаются). Права
    подсказываются из permission_catalog.py и из уже сохранённых
    записей ModulePermission в БД.
    """
    from src.core.utils.module_registry import get_disabled_modules, get_installed_module_names

    disabled = get_disabled_modules()
    permission_catalogs = _get_cache()['catalogs']
    modules: List[Dict[str, Any]] = []

    for module_name in get_installed_module_names(include_disabled=include_disabled):
        catalog = permission_catalogs.get(module_name)
        permissions = dict(catalog.get('permissions', {})) if catalog else {}
        modules.append({
            'module_name': module_name,
            'module_label': _resolve_module_label(module_name, catalog),
            'has_permission_catalog': bool(catalog and catalog.get('permissions')),
            'permissions': permissions,
            'disabled': module_name in disabled,
        })

    _merge_stored_module_permissions(modules, disabled=disabled)
    return modules


def clear_cache() -> None:
    """Сбрасывает кеш (например, при горячей перезагрузке)."""
    global _catalog_cache
    _catalog_cache = None
