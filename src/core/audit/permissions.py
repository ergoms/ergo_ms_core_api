"""Права доступа к центральному журналу аудита."""

from rest_framework.permissions import BasePermission

from src.core.cms.adp.services.permissions import PermissionService
from src.core.integrations import bridge
from src.core.integrations.module_contracts import AUDIT_CAN_READ

from .dimensions import get_read_guard_dimensions


class CanReadAuditLog(BasePermission):
    """Глобальный админ — всегда; иначе — решение владельца read_guard-измерения.

    Не-админ должен иметь значения всех read_guard-измерений в контексте запроса
    (их резолвит модуль-владелец из request), и модуль-владелец через
    ``audit.can_read`` подтверждает право читать журнал в этом scope.
    """

    message = 'Недостаточно прав для просмотра журнала аудита'

    def has_permission(self, request, view) -> bool:
        user = getattr(request, 'user', None)
        if not user or not user.is_authenticated:
            return False

        if PermissionService.is_admin(user):
            return True

        read_guard = get_read_guard_dimensions()
        if not read_guard:
            return False

        scope: dict = {}
        for dim in read_guard:
            resolve = dim.get('resolve')
            value = resolve(request) if callable(resolve) else None
            if value in (None, ''):
                return False
            scope[dim['key']] = value

        result = bridge.emit_first(
            AUDIT_CAN_READ,
            user=user,
            scope=scope,
            request=request,
        )
        return result is True
