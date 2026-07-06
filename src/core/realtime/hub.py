from __future__ import annotations

import logging
from typing import Any

from asgiref.sync import async_to_sync
from channels.layers import get_channel_layer

from src.core.realtime.channel_message import build_channel_message

logger = logging.getLogger('core.realtime')


class RealtimeHub:
    """Транспортно-независимая публикация realtime-событий через channel layer."""

    @staticmethod
    def publish(
        *,
        group: str,
        topic: str,
        event_type: str,
        payload: Any,
    ) -> None:
        channel_layer = get_channel_layer()
        if channel_layer is None:
            logger.warning('Channel layer недоступен, событие %s не отправлено', event_type)
            return

        message = build_channel_message(topic=topic, event_type=event_type, payload=payload)

        try:
            async_to_sync(channel_layer.group_send)(group, message)
        except Exception:
            logger.exception('RealtimeHub.publish failed: group=%s type=%s', group, event_type)

    @staticmethod
    async def publish_async(
        channel_layer,
        *,
        group: str,
        topic: str,
        event_type: str,
        payload: Any,
    ) -> None:
        message = build_channel_message(topic=topic, event_type=event_type, payload=payload)
        await channel_layer.group_send(group, message)
