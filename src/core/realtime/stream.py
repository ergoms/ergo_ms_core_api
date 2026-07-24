from __future__ import annotations

import asyncio
import json
import logging
from collections.abc import AsyncIterator

from channels.db import database_sync_to_async
from channels.layers import get_channel_layer
from django.conf import settings

from src.core.realtime.subscriptions import clear_user_subscriptions, groups_for_user

logger = logging.getLogger('core.realtime')

_SSE_JSON_SEPARATORS = (',', ':')


def _encode_sse_data(payload: dict) -> str:
    return f'data: {json.dumps(payload, ensure_ascii=False, separators=_SSE_JSON_SEPARATORS)}\n\n'


async def sse_event_stream(user) -> AsyncIterator[str]:
    channel_layer = get_channel_layer()
    if channel_layer is None:
        yield 'event: error\ndata: {"message":"channel_layer_unavailable"}\n\n'
        return

    channel_name = await channel_layer.new_channel()
    subscribed_groups: set[str] = set()
    keepalive = getattr(settings, 'REALTIME_SSE_KEEPALIVE_INTERVAL', 25)

    async def sync_groups() -> None:
        nonlocal subscribed_groups
        target_groups = set(await database_sync_to_async(groups_for_user)(user))
        for group in target_groups - subscribed_groups:
            await channel_layer.group_add(group, channel_name)
        for group in subscribed_groups - target_groups:
            await channel_layer.group_discard(group, channel_name)
        subscribed_groups = target_groups

    await sync_groups()

    try:
        while True:
            try:
                message = await asyncio.wait_for(
                    channel_layer.receive(channel_name),
                    timeout=keepalive,
                )
                if message.get('type') == 'sse_resync':
                    await sync_groups()
                    continue

                envelope = message.get('envelope')
                if envelope:
                    yield _encode_sse_data(envelope)
            except asyncio.TimeoutError:
                await sync_groups()
                yield ': ping\n\n'
            except asyncio.CancelledError:
                raise
            except Exception:
                logger.exception('SSE stream error for user_id=%s', user.pk)
                yield ': ping\n\n'
    finally:
        for group in subscribed_groups:
            try:
                await channel_layer.group_discard(group, channel_name)
            except Exception:
                pass
        clear_user_subscriptions(user.pk)
