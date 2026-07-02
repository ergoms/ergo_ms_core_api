# -*- coding: utf-8 -*-
"""Проверка видимости пункта меню для пользователя."""

from src.core.cms.adp.models import UserRole
from src.core.cms.adp.services.permissions import PermissionService
from src.core.integrations import bridge


def user_can_see_menu_item(item, user) -> bool:
    """
    is_admin_only, allowed_roles, allowed_role_groups.
    Ограничение по правам модуля — через M2M allowed_role_groups на пункте.
    Модули могут переопределить видимость через событие menu.can_see_item.
    """
    menu_override = bridge.emit_first('menu.can_see_item', item=item, user=user)
    if menu_override is not None:
        return bool(menu_override)

    if PermissionService.is_admin(user):
        return True

    user_role = UserRole.objects.filter(user=user, is_active=True).first()

    if item.is_admin_only:
        if not user_role or user_role.role.role_type != 'admin':
            return False

    if item.allowed_roles.exists():
        if not user_role or not item.allowed_roles.filter(id=user_role.role.id).exists():
            return False

    if item.allowed_role_groups.exists():
        if not user_role:
            return False
        user_groups = user_role.role_groups.all()
        if not item.allowed_role_groups.filter(
            id__in=user_groups.values_list('id', flat=True)
        ).exists():
            return False

    return True
