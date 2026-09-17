"""Регистрация topic ядра в realtime registry."""

from src.core.cms.adp.services.permissions import PermissionService
from src.core.realtime.registry import register_realtime_topic
from src.core.realtime.room_access import has_messenger_access, resolve_room_object_pk
from src.core.realtime.topics import (
    PRESENCE_ADMIN_GROUP,
    PRESENCE_ADMIN_TOPIC,
    PRESENCE_PEER_TOPIC_PATTERN,
    messenger_group,
    notifications_user_group,
    presence_peer_group,
)

_registered = False


def _authorize_user_topic(user, params: dict[str, str]) -> bool:
    try:
        uid = int(params['user_id'])
    except (KeyError, TypeError, ValueError):
        return False
    return user.pk == uid


def _resolve_user_topic(user, params: dict[str, str]) -> str | None:
    try:
        uid = int(params['user_id'])
    except (KeyError, TypeError, ValueError):
        return None
    if user.pk != uid:
        return None
    return notifications_user_group(uid)


def _authorize_messenger_topic(user, params: dict[str, str]) -> bool:
    content_type = params.get('content_type', '')
    object_id = params.get('object_id', '')
    if not content_type or object_id in (None, ''):
        return False
    return has_messenger_access(user, content_type, object_id)


def _resolve_messenger_topic(_user, params: dict[str, str]) -> str | None:
    content_type = params.get('content_type', '')
    object_id = params.get('object_id', '')
    if not content_type or object_id in (None, ''):
        return None
    object_pk = resolve_room_object_pk(content_type, object_id)
    if object_pk is None:
        return None
    return messenger_group(content_type, object_pk)


def _authorize_presence_admin(user, _params: dict[str, str]) -> bool:
    return PermissionService.can_manage_users_as_global_admin(user)


def _resolve_presence_admin(_user, _params: dict[str, str]) -> str | None:
    return PRESENCE_ADMIN_GROUP


def _authorize_presence_peer(user, params: dict[str, str]) -> bool:
    if user is None or not getattr(user, 'is_authenticated', False):
        return False
    public_id = str(params.get('public_id') or '').strip()
    return bool(public_id) and not public_id.isdigit()


def _resolve_presence_peer(_user, params: dict[str, str]) -> str | None:
    public_id = str(params.get('public_id') or '').strip()
    if not public_id or public_id.isdigit():
        return None
    return presence_peer_group(public_id)


def register_core_realtime_topics() -> None:
    global _registered
    if _registered:
        return
    _registered = True
    register_realtime_topic(
        'user:{user_id}',
        authorize=_authorize_user_topic,
        resolve_group=_resolve_user_topic,
    )
    register_realtime_topic(
        'messenger:{content_type}:{object_id}',
        authorize=_authorize_messenger_topic,
        resolve_group=_resolve_messenger_topic,
    )
    register_realtime_topic(
        PRESENCE_ADMIN_TOPIC,
        authorize=_authorize_presence_admin,
        resolve_group=_resolve_presence_admin,
    )
    register_realtime_topic(
        PRESENCE_PEER_TOPIC_PATTERN,
        authorize=_authorize_presence_peer,
        resolve_group=_resolve_presence_peer,
    )
