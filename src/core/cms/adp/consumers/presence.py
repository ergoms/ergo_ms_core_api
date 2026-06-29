import asyncio
import logging

from channels.db import database_sync_to_async
from channels.generic.websocket import AsyncJsonWebsocketConsumer

from src.core.cms.adp.services import presence as presence_service
from src.core.cms.adp.services.permissions import PermissionService
from src.core.cms.adp.ws_auth import authenticate_ws_scope

logger = logging.getLogger('core.cms.adp')

PRESENCE_ADMIN_SNAPSHOT_INTERVAL = 10


class PresenceConsumer(AsyncJsonWebsocketConsumer):
    """WebSocket presence текущего пользователя: ws/presence/?token=<JWT>."""

    user_id: int | None = None

    async def connect(self):
        user = await authenticate_ws_scope(self.scope)
        if user is None or not getattr(user, 'is_authenticated', False):
            await self.close(code=4401)
            return

        self.scope['user'] = user
        self.user_id = user.pk
        await self._register_connection(self.user_id)
        await self.accept()

    async def disconnect(self, close_code):
        if self.user_id is not None:
            await self._unregister_connection(self.user_id)

    async def receive_json(self, content, **kwargs):
        if content.get('type') != 'ping' or self.user_id is None:
            return
        await self._touch(self.user_id)

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


class PresenceAdminConsumer(AsyncJsonWebsocketConsumer):
    """Admin feed presence snapshot: ws/presence/admin/?token=<JWT>."""

    snapshot_task: asyncio.Task | None = None

    async def connect(self):
        user = await authenticate_ws_scope(self.scope)
        if user is None or not getattr(user, 'is_authenticated', False):
            await self.close(code=4401)
            return

        if not await self._is_global_admin(user):
            await self.close(code=4403)
            return

        self.scope['user'] = user
        await self.accept()
        await self._send_snapshot()
        self.snapshot_task = asyncio.create_task(self._snapshot_loop())

    async def disconnect(self, close_code):
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
        await self.send_json({
            'type': 'presence_snapshot',
            'users': users,
        })

    @staticmethod
    @database_sync_to_async
    def _build_snapshot():
        return presence_service.build_presence_snapshot()

    @staticmethod
    @database_sync_to_async
    def _is_global_admin(user):
        return PermissionService.can_manage_users_as_global_admin(user)
