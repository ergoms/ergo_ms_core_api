from rest_framework.permissions import BasePermission

from src.core.cms.adp.services.permissions import PermissionService


class IsGlobalAdmin(BasePermission):
    """Глобальный администратор: UserRole «Администратор» или is_superuser."""

    message = 'Доступ запрещён. Требуются права администратора.'

    def has_permission(self, request, view) -> bool:
        user = getattr(request, 'user', None)
        if not user or not user.is_authenticated:
            return False
        return PermissionService.can_manage_users_as_global_admin(user)
