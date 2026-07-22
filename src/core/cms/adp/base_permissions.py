"""
Базовые классы permissions для модулей системы.

Проверка прав к функционалу модулей через PermissionService. Контекст scope —
опциональный: модуль-владелец домена объявляет ``scope_type``, и тогда id
соответствующей сущности извлекается из запроса и передаётся в проверку прав.
Ядро не знает конкретных scope-типов.
"""
from rest_framework.permissions import BasePermission

from .services import PermissionService


class BaseModulePermission(BasePermission):
    """
    Базовый permission для прав модулей через PermissionService.
    
    Наследуйте от этого класса в модулях и переопределите:
    - module_name: str — название модуля
    - required_permission: str | None — ключ требуемого разрешения
    - scope_type: str | None — тип scope-контекста, объявляемый модулем;
      если задан, id сущности передаётся в проверку как ``{scope_type}_id``
    
    Пример использования:
    
        class CanViewProjects(BaseModulePermission):
            module_name = "my_module"
            required_permission = "project_view"
    """
    
    module_name: str = None
    required_permission: str | None = None
    scope_type: str | None = None

    def _get_scope_id(self, request, view, scope_type: str) -> int | None:
        """
        Извлечь id scope-сущности из запроса.

        Проверяет для scope_type='foo':
        1. Query params: ?foo_id=123
        2. Request body: {"foo_id": 123} или {"foo": 123}
        3. URL kwargs: /.../<foo_id>/... или /.../<foo_pk>/...
        """
        def _as_int(value):
            if value in (None, ''):
                return None
            try:
                return int(value)
            except (ValueError, TypeError):
                return None

        # Из query params
        scope_id = _as_int(request.query_params.get(f'{scope_type}_id'))
        if scope_id is not None:
            return scope_id

        # Из body (для POST/PUT/PATCH)
        if hasattr(request, 'data') and request.data:
            scope_id = _as_int(
                request.data.get(f'{scope_type}_id') or request.data.get(scope_type)
            )
            if scope_id is not None:
                return scope_id

        # Из URL kwargs (для nested routes)
        if hasattr(view, 'kwargs') and view.kwargs:
            scope_id = _as_int(
                view.kwargs.get(f'{scope_type}_id') or view.kwargs.get(f'{scope_type}_pk')
            )
            if scope_id is not None:
                return scope_id

        return None

    def _scope_kwargs(self, request, view) -> dict:
        """Контекст scope для передачи в проверку прав ({scope_type}_id=...)."""
        if not self.scope_type:
            return {}
        return {f'{self.scope_type}_id': self._get_scope_id(request, view, self.scope_type)}

    def has_permission(self, request, view) -> bool:
        """
        Проверить право доступа.
        
        Иерархия проверки:
        1. Пользователь должен быть аутентифицирован
        2. Если required_permission не задан — разрешить
        3. Проверить права через PermissionService с учётом scope-контекста
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

        return PermissionService.check_module_permission(
            user=user,
            module_name=self.module_name,
            permission_key=self.required_permission,
            **self._scope_kwargs(request, view),
        )

