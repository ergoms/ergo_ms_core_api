from __future__ import annotations

import logging
import threading

from asgiref.sync import async_to_sync
from channels.layers import get_channel_layer

from src.core.cms.adp.services.permissions import PermissionService
from src.core.realtime.registry import authorize_registered_topic
from src.core.realtime.topics import (
    PRESENCE_ADMIN_GROUP,
    PRESENCE_ADMIN_TOPIC,
    notifications_user_group,
    sse_control_group,
)

logger = logging.getLogger('core.realtime')

_lock = threading.Lock()
_user_topics: dict[int, set[str]] = {}


def _user_topic_set(user_id: int) -> set[str]:
    with _lock:
        return set(_user_topics.get(user_id, set()))


def notify_sse_resync(user_id: int) -> None:
    """Мгновенный resync групп SSE-потока (без reconnect клиента)."""
    channel_layer = get_channel_layer()
    if channel_layer is None:
        return
    try:
        async_to_sync(channel_layer.group_send)(
            sse_control_group(user_id),
            {'type': 'sse_resync'},
        )
    except Exception:
        logger.exception('notify_sse_resync failed user_id=%s', user_id)


def subscribe_topic(user, topic: str) -> tuple[bool, str | None]:
    """Подписать пользователя на topic. Возвращает (ok, group_name)."""
    group = resolve_topic_to_group(user, topic)
    if group is None:
        return False, None
    with _lock:
        _user_topics.setdefault(user.pk, set()).add(topic)
    notify_sse_resync(user.pk)
    return True, group


def unsubscribe_topic(user, topic: str) -> tuple[bool, str | None]:
    group = resolve_topic_to_group(user, topic)
    with _lock:
        topics = _user_topics.get(user.pk)
        if topics is not None:
            topics.discard(topic)
            if not topics:
                _user_topics.pop(user.pk, None)
    notify_sse_resync(user.pk)
    return True, group


def groups_for_user(user) -> list[str]:
    groups = [
        notifications_user_group(user.pk),
        sse_control_group(user.pk),
    ]
    for topic in _user_topic_set(user.pk):
        group = resolve_topic_to_group(user, topic)
        if group and group not in groups:
            groups.append(group)
    if PermissionService.can_manage_users_as_global_admin(user):
        if PRESENCE_ADMIN_TOPIC in _user_topic_set(user.pk):
            if PRESENCE_ADMIN_GROUP not in groups:
                groups.append(PRESENCE_ADMIN_GROUP)
    return groups


def resolve_topic_to_group(user, topic: str) -> str | None:
    return authorize_registered_topic(user, topic)


def clear_user_subscriptions(user_id: int) -> None:
    with _lock:
        _user_topics.pop(user_id, None)
