from __future__ import annotations

import logging
import threading
import time

from src.core.realtime.hub import RealtimeHub
from src.core.realtime.topics import PRESENCE_ADMIN_GROUP, PRESENCE_ADMIN_TOPIC

logger = logging.getLogger('core.cms.adp')

_THROTTLE_SEC = 2.0
_last_publish: dict[int, float] = {}
_lock = threading.Lock()


def publish_presence_delta(user_id: int, entry: dict) -> None:
    """Push изменения presence админам (SSE / WS), с throttle по user_id."""
    now = time.monotonic()
    with _lock:
        last = _last_publish.get(user_id, 0.0)
        if now - last < _THROTTLE_SEC:
            return
        _last_publish[user_id] = now

    payload = {
        'user_id': user_id,
        **entry,
    }
    try:
        RealtimeHub.publish(
            group=PRESENCE_ADMIN_GROUP,
            topic=PRESENCE_ADMIN_TOPIC,
            event_type='presence_delta',
            payload={'users': [payload]},
        )
    except Exception:
        logger.exception('publish_presence_delta failed user_id=%s', user_id)


def publish_presence_snapshot(users: list) -> None:
    """Полный snapshot presence для админов (WS / SSE)."""
    try:
        RealtimeHub.publish(
            group=PRESENCE_ADMIN_GROUP,
            topic=PRESENCE_ADMIN_TOPIC,
            event_type='presence_snapshot',
            payload={'users': users},
        )
    except Exception:
        logger.exception('publish_presence_snapshot failed')
