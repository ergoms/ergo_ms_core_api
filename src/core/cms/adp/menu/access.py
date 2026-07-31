# -*- coding: utf-8 -*-
"""Проверка видимости пункта меню для пользователя."""

from src.core.cms.adp.services.permissions import PermissionService
from src.core.integrations import bridge
from src.core.integrations.module_contracts import (
    MENU_CAN_SEE_ITEM,
    MENU_PREPARE_VISIBILITY,
)


def _collect_route_overrides(user) -> dict[str, bool]:
    """Один проход bridge.prepare_visibility вместо emit_first на каждый пункт."""
    overrides: dict[str, bool] = {}
    for result in bridge.emit(MENU_PREPARE_VISIBILITY, user=user):
        if not isinstance(result, dict):
            continue
        for route_name, visible in result.items():
            if route_name and visible is not None:
                overrides[str(route_name)] = bool(visible)
    return overrides


class MenuAccessChecker:
    """Контекст проверки прав на пункты меню за один запрос."""

    def __init__(self, user):
        self.user = user
        self._is_admin = PermissionService.is_admin(user)
        self._route_overrides = _collect_route_overrides(user)

    def _load_user_role(self):
        return PermissionService.get_user_role(self.user)

    def can_see(self, item) -> bool:
        from src.core.utils.module_registry import (
            is_module_disabled,
            top_level_module_from_menu_source,
        )

        module_source = getattr(item, 'module_source', '') or ''
        top_level = top_level_module_from_menu_source(module_source)
        if top_level and is_module_disabled(top_level):
            return False

        route_name = getattr(item, 'route_name', None)
        if route_name and route_name in self._route_overrides:
            return self._route_overrides[route_name]

        menu_override = bridge.emit_first(MENU_CAN_SEE_ITEM, item=item, user=self.user)
        if menu_override is not None:
            return bool(menu_override)

        if self._is_admin:
            return True

        user_role = self._load_user_role()

        if item.is_admin_only:
            if not user_role or user_role.role.role_type != 'admin':
                return False

        allowed_roles = list(item.allowed_roles.all())
        if allowed_roles:
            if not user_role or not any(role.id == user_role.role_id for role in allowed_roles):
                return False

        allowed_groups = list(item.allowed_role_groups.all())
        if allowed_groups:
            if not user_role:
                return False
            user_group_ids = {group.id for group in user_role.role_groups.all()}
            if not any(group.id in user_group_ids for group in allowed_groups):
                return False

        return True


def user_can_see_menu_item(item, user, *, checker: MenuAccessChecker | None = None) -> bool:
    """
    is_admin_only, allowed_roles, allowed_role_groups.
    Ограничение по правам модуля — через M2M allowed_role_groups на пункте.
    Модули могут переопределить видимость через событие menu.can_see_item.
    """
    if checker is not None:
        return checker.can_see(item)
    return MenuAccessChecker(user).can_see(item)
