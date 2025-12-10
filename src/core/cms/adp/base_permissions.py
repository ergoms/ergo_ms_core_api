"""
Базовые классы permissions для модулей системы.

Используется для проверки прав доступа к функционалу модулей
с поддержкой контекста организации.
"""
from rest_framework.permissions import BasePermission

from .services import PermissionService


class BaseModulePermission(BasePermission):
    """
    Базовый permission для прав модулей через PermissionService.
    
    Наследуйте от этого класса в модулях и переопределите:
    - module_name: str — название модуля
    - required_permission: str | None — ключ требуемого разрешения
    
    Пример использования:
    
        class CanViewProjects(BaseModulePermission):
            module_name = "projects"
            required_permission = "project_view"
    """
    
    module_name: str = None
    required_permission: str | None = None

    def _get_organization_id(self, request, view) -> int | None:
        """
        Извлечь organization_id из запроса.
        
        Проверяет:
        1. Query params: ?organization_id=123
        2. Request body: {"organization_id": 123} или {"organization": 123}
        3. URL kwargs: /organizations/<organization_id>/... или /organizations/<organization_pk>/...
        """
        # Из query params
        org_id = request.query_params.get('organization_id')
        if org_id:
            try:
                return int(org_id)
            except (ValueError, TypeError):
                pass
        
        # Из body (для POST/PUT/PATCH)
        if hasattr(request, 'data') and request.data:
            org_id = request.data.get('organization_id') or request.data.get('organization')
            if org_id:
                try:
                    return int(org_id)
                except (ValueError, TypeError):
                    pass
        
        # Из URL kwargs (для nested routes)
        if hasattr(view, 'kwargs') and view.kwargs:
            org_id = view.kwargs.get('organization_id') or view.kwargs.get('organization_pk')
            if org_id:
                try:
                    return int(org_id)
                except (ValueError, TypeError):
                    pass
        
        return None

    def has_permission(self, request, view) -> bool:
        """
        Проверить право доступа.
        
        Иерархия проверки:
        1. Пользователь должен быть аутентифицирован
        2. Если required_permission не задан — разрешить
        3. Проверить права через PermissionService с учётом контекста организации
        """
        user = getattr(request, "user", None)
        if not user or not user.is_authenticated:
            return False

        if not self.required_permission:
            return True
        
        if not self.module_name:
            raise ValueError(
                f"{self.__class__.__name__}: module_name не задан. "
                "Переопределите атрибут module_name в классе."
            )

        organization_id = self._get_organization_id(request, view)

        return PermissionService.check_module_permission(
            user=user,
            module_name=self.module_name,
            permission_key=self.required_permission,
            organization_id=organization_id,
        )

