"""Кэш сериализованного snapshot прав пользователя (Django cache)."""

from __future__ import annotations

import logging

from django.conf import settings
from django.contrib.auth.models import User
from django.core.cache import cache

from src.core.cms.adp.serializers import UserPermissionsSerializer
from src.core.cms.adp.services.permissions import PermissionService

logger = logging.getLogger('core.cms.adp.permissions')

_SNAPSHOT_PREFIX = 'perms_snapshot:'
_VERSION_PREFIX = 'perms_snapshot:ver:'
_GLOBAL_VERSION_KEY = 'perms_snapshot:global_ver'


def get_permissions_snapshot_ttl() -> int:
    return max(0, int(getattr(settings, 'PERMISSIONS_SNAPSHOT_CACHE_TTL', 60) or 0))


def _version_key(user_id: int) -> str:
    return f'{_VERSION_PREFIX}{user_id}'


def _snapshot_key(user_id: int) -> str:
    global_ver = int(cache.get(_GLOBAL_VERSION_KEY, 0) or 0)
    user_ver = int(cache.get(_version_key(user_id), 0) or 0)
    return f'{_SNAPSHOT_PREFIX}g{global_ver}:u{user_id}:v{user_ver}'


def invalidate_user_permissions_snapshot(user_id: int | None) -> None:
    if user_id is None:
        return
    key = _version_key(int(user_id))
    cache.set(key, int(cache.get(key, 0) or 0) + 1, timeout=None)


def invalidate_all_permissions_snapshots() -> None:
    cache.set(
        _GLOBAL_VERSION_KEY,
        int(cache.get(_GLOBAL_VERSION_KEY, 0) or 0) + 1,
        timeout=None,
    )


def get_user_permissions_payload(user: User) -> dict:
    """Сериализованные права; кэш в Django cache с TTL."""
    if user is None or not getattr(user, 'pk', None):
        return _build_payload(user)

    ttl = get_permissions_snapshot_ttl()
    if ttl <= 0:
        return _build_payload(user)

    cache_key = _snapshot_key(user.pk)
    cached = cache.get(cache_key)
    if cached is not None:
        return cached

    payload = _build_payload(user)
    cache.set(cache_key, payload, timeout=ttl)
    return payload


def _build_payload(user: User) -> dict:
    permissions = PermissionService.get_user_permissions(user)
    return UserPermissionsSerializer(permissions).data
