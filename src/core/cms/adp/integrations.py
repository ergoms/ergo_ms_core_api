"""Platform-ops ADP для распределённого входа и прав."""

from __future__ import annotations

from src.core.cms.adp.services.session_devices import is_device_session_active
from src.core.integrations import bridge
from src.core.integrations.module_contracts import (
    ADP_CHECK_API_ACCESS,
    ADP_CHECK_MODULE_PERMISSION,
    ADP_IS_ADMIN,
    SESSION_DEVICE_ACTIVE,
)


def _resolve_user(*, user_id=None, user_public_id=None):
    from django.contrib.auth import get_user_model

    User = get_user_model()
    user = None
    if user_id is not None:
        user = User.objects.filter(pk=user_id).first()
    if user is None and user_public_id:
        user = User.objects.filter(public_id=user_public_id).first()
    if user is None or not user.is_active:
        return None
    return user


@bridge.provide_op(SESSION_DEVICE_ACTIVE)
def _session_device_active(*, user_id=None, device_id=None, user_public_id=None, **_):
    if device_id is None:
        return False
    user = _resolve_user(user_id=user_id, user_public_id=user_public_id)
    if user is None:
        return False
    return bool(is_device_session_active(user, device_id))


@bridge.provide_op(ADP_IS_ADMIN)
def _adp_is_admin(*, user_id=None, user_public_id=None, **_):
    from src.core.cms.adp.services.permissions import PermissionService

    user = _resolve_user(user_id=user_id, user_public_id=user_public_id)
    if user is None:
        return False
    return bool(PermissionService.is_admin(user))


@bridge.provide_op(ADP_CHECK_API_ACCESS)
def _adp_check_api_access(*, user_id=None, user_public_id=None, api_path='', **_):
    from src.core.cms.adp.services.permissions import PermissionService

    user = _resolve_user(user_id=user_id, user_public_id=user_public_id)
    if user is None:
        return False
    return bool(PermissionService.check_api_access(user, api_path or ''))


@bridge.provide_op(ADP_CHECK_MODULE_PERMISSION)
def _adp_check_module_permission(
    *,
    user_id=None,
    user_public_id=None,
    module_name='',
    permission_key='',
    extra=None,
    **_,
):
    from src.core.cms.adp.services.permissions import PermissionService

    user = _resolve_user(user_id=user_id, user_public_id=user_public_id)
    if user is None:
        return False
    kwargs = extra if isinstance(extra, dict) else {}
    return bool(
        PermissionService.check_module_permission(
            user,
            module_name,
            permission_key,
            **kwargs,
        )
    )
