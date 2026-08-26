"""Права ADP с процесса модуля: JWT-principal, роль и политики — на ядре."""

from __future__ import annotations

from django.conf import settings

from src.core.integrations import bridge
from src.core.integrations.module_contracts import (
    ADP_CHECK_API_ACCESS,
    ADP_CHECK_MODULE_PERMISSION,
    ADP_IS_ADMIN,
)


def jwt_claims_on_module() -> bool:
    mode = (getattr(settings, 'MODULE_AUTH_MODE', 'orm') or 'orm').strip().lower()
    if mode != 'jwt_claims':
        return False
    role = (getattr(settings, 'ERGO_PROCESS_ROLE', '') or '').strip().lower()
    return role.startswith('module:')


def user_pk(user) -> int | None:
    raw = getattr(user, 'pk', None)
    if raw is None:
        raw = getattr(user, 'id', None)
    if raw is None:
        return None
    try:
        return int(raw)
    except (TypeError, ValueError):
        return None


def user_public_id_str(user) -> str:
    pid = getattr(user, 'public_id', None)
    return str(pid) if pid else ''


def _remote_kwargs(user) -> dict:
    return {
        'user_id': user_pk(user),
        'user_public_id': user_public_id_str(user),
    }


def remote_is_admin(user) -> bool:
    result = bridge.call(ADP_IS_ADMIN, default=None, **_remote_kwargs(user))
    if result is None:
        return False
    return bool(result)


def remote_check_api_access(user, api_path: str) -> bool:
    result = bridge.call(
        ADP_CHECK_API_ACCESS,
        default=None,
        api_path=api_path,
        **_remote_kwargs(user),
    )
    if result is None:
        return bool(getattr(user, 'is_authenticated', False))
    return bool(result)


def remote_check_module_permission(
    user,
    module_name: str,
    permission_key: str,
    extra: dict,
) -> bool:
    result = bridge.call(
        ADP_CHECK_MODULE_PERMISSION,
        default=None,
        module_name=module_name,
        permission_key=permission_key,
        extra=extra or {},
        **_remote_kwargs(user),
    )
    if result is None:
        return bool(getattr(user, 'is_authenticated', False))
    return bool(result)
