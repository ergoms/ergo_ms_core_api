"""
Сервисы модуля ADP
"""
from .permissions import (
    PermissionService,
    register_permission_hook,
    unregister_permission_hook,
)
from .permission_catalog import (
    get_all_permission_keys,
    get_module_names,
    resolve_module_name,
    get_module_permission_keys,
)

__all__ = [
    'PermissionService',
    'register_permission_hook',
    'unregister_permission_hook',
    'get_all_permission_keys',
    'get_module_names',
    'resolve_module_name',
    'get_module_permission_keys',
]
