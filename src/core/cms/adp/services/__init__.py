"""
Сервисы модуля ADP
"""
from .permissions import (
    PermissionService,
    register_permission_hook,
    unregister_permission_hook,
)

__all__ = [
    'PermissionService',
    'register_permission_hook',
    'unregister_permission_hook',
]
