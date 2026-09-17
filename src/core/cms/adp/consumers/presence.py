import asyncio
import logging

from channels.db import database_sync_to_async

from src.core.cms.adp.consumers.base import JwtMessageAuthConsumer, WsAuthRejectedError
from src.core.cms.adp.services import presence as presence_service
from src.core.cms.adp.services.permissions import PermissionService
from src.core.cms.adp.services.presence_realtime import publish_presence_snapshot
from src.core.realtime.consumer_mixin import RealtimeEnvelopeConsumerMixin
from src.core.realtime.envelope import PRESENCE_PING_EVENT, PRESENCE_WATCH_EVENT, parse_envelope
from src.core.realtime.topics import PRESENCE_ADMIN_GROUP, presence_peer_group

logger = logging.getLogger('core.cms.adp')

PRESENCE_ADMIN_SNAPSHOT_INTERVAL = 10


class PresenceConsumer(RealtimeEnvelopeConsumerMixin, JwtMessageAuthConsumer):
    """WebSocket presence текущего пользователя: ws/presence/ + auth-сообщение."""

    user_id: int | None = None

    async def connect(self):
        self._watched_ids: set[str] = set()
        await super().connect()

    async def on_ws_authenticated(self):
        self.user_id = self.ws_user.pk
        await self._register_connection(self.user_id)

    async def on_ws_disconnect(self, close_code):
        await self._sync_watched_ids(set())
        if self.user_id is not None:
            await self._unregister_connection(self.user_id)

    async def receive_authenticated_json(self, content, **kwargs):
        if self.user_id is None:
            return
        envelope = parse_envelope(content)
        if envelope is None:
            return
        event_type = envelope.get('type')
        if event_type == PRESENCE_PING_EVENT:
            await self._touch(self.user_id)
            return
        if event_type == PRESENCE_WATCH_EVENT:
            await self._sync_watched_ids(set(
                presence_service.parse_watch_public_ids(envelope.get('payload')),
            ))

    async def _sync_watched_ids(self, new_ids: set[str]):
        current = getattr(self, '_watched_ids', set())
        channel_layer = self.channel_layer
        if channel_layer is None:
            self._watched_ids = new_ids
            return
        for public_id in current - new_ids:
            await channel_layer.group_discard(
                presence_peer_group(public_id),
                self.channel_name,
            )
        for public_id in new_ids - current:
            await channel_layer.group_add(
                presence_peer_group(public_id),
                self.channel_name,
            )
        self._watched_ids = new_ids

    @staticmethod
    @database_sync_to_async
    def _register_connection(user_id: int):
        presence_service.register_connection(user_id)

    @staticmethod
    @database_sync_to_async
    def _unregister_connection(user_id: int):
        presence_service.unregister_connection(user_id)

    @staticmethod
    @database_sync_to_async
    def _touch(user_id: int):
        presence_service.touch(user_id)


class PresenceAdminConsumer(RealtimeEnvelopeConsumerMixin, JwtMessageAuthConsumer):
    """Admin feed presence snapshot: ws/presence/admin/ + auth-сообщение."""

    snapshot_task: asyncio.Task | None = None
    _admin_group: str | None = None

    async def on_ws_authenticated(self):
        if not await self._is_global_admin(self.ws_user):
            raise WsAuthRejectedError(4403)

        self._admin_group = PRESENCE_ADMIN_GROUP
        await self.channel_layer.group_add(self._admin_group, self.channel_name)
        await self._send_snapshot()
        self.snapshot_task = asyncio.create_task(self._snapshot_loop())

    async def on_ws_disconnect(self, close_code):
        if self._admin_group:
            await self.channel_layer.group_discard(self._admin_group, self.channel_name)
            self._admin_group = None
        if self.snapshot_task is not None:
            self.snapshot_task.cancel()
            try:
                await self.snapshot_task
            except asyncio.CancelledError:
                pass
            self.snapshot_task = None

    async def _snapshot_loop(self):
        try:
            while True:
                await asyncio.sleep(PRESENCE_ADMIN_SNAPSHOT_INTERVAL)
                await self._send_snapshot()
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception('Ошибка цикла presence snapshot для админа')

    async def _send_snapshot(self):
        users = await self._build_snapshot()
        await database_sync_to_async(publish_presence_snapshot)(users)

    @staticmethod
    @database_sync_to_async
    def _build_snapshot():
        return presence_service.build_presence_snapshot()

    @staticmethod
    @database_sync_to_async
    def _is_global_admin(user):
        return PermissionService.can_manage_users_as_global_admin(user)
