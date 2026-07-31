"""Управление пользователями в админ-панели."""
from src.core.cms.adp.views_admin_users_account import (
    AdminUserResetPasswordView,
    AdminUserStatusView,
)
from src.core.cms.adp.views_admin_users_detail import (
    AdminUserAvatarView,
    AdminUserDetailView,
)
from src.core.cms.adp.views_admin_users_list import AdminUserRoleListView
from src.core.cms.adp.views_admin_users_sessions import (
    AdminUserDeviceDetailView,
    AdminUserDevicesView,
    AdminUserRevokeSessionsView,
)

__all__ = [
    'AdminUserRoleListView',
    'AdminUserDetailView',
    'AdminUserAvatarView',
    'AdminUserResetPasswordView',
    'AdminUserStatusView',
    'AdminUserDevicesView',
    'AdminUserDeviceDetailView',
    'AdminUserRevokeSessionsView',
]
