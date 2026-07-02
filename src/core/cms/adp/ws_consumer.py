import asyncio
import logging

from channels.generic.websocket import AsyncJsonWebsocketConsumer

from src.core.cms.adp.ws_auth import user_from_jwt_token

logger = logging.getLogger('core.cms.adp')

WS_AUTH_MESSAGE_TYPE = 'auth'
WS_AUTH_OK_TYPE = 'auth_ok'
WS_AUTH_TIMEOUT_SEC = 10
WS_AUTH_CLOSE_UNAUTHORIZED = 4401


class JwtMessageAuthConsumer(AsyncJsonWebsocketConsumer):
    """WebSocket с JWT-аутентификацией через первое JSON-сообщение (без token в URL)."""

    user = None
    _auth_pending = False
    _auth_timeout_task: asyncio.Task | None = None

    async def connect(self):
        self._auth_pending = True
        await self.accept()
        self._auth_timeout_task = asyncio.create_task(self._close_on_auth_timeout())

    async def disconnect(self, close_code):
        if self._auth_timeout_task is not None:
            self._auth_timeout_task.cancel()
            try:
                await self._auth_timeout_task
            except asyncio.CancelledError:
                pass
            self._auth_timeout_task = None

    async def receive_json(self, content, **kwargs):
        if self._auth_pending:
            await self._handle_auth_message(content)
            return
        await self.receive_authenticated_json(content, **kwargs)

    async def receive_authenticated_json(self, content, **kwargs):
        return

    async def on_authenticated(self, user):
        return

    async def _close_on_auth_timeout(self):
        try:
            await asyncio.sleep(WS_AUTH_TIMEOUT_SEC)
            if self._auth_pending:
                await self.close(code=WS_AUTH_CLOSE_UNAUTHORIZED)
        except asyncio.CancelledError:
            raise

    async def _handle_auth_message(self, content):
        if content.get('type') != WS_AUTH_MESSAGE_TYPE:
            await self.close(code=WS_AUTH_CLOSE_UNAUTHORIZED)
            return

        token = content.get('token')
        if not token or not isinstance(token, str):
            await self.close(code=WS_AUTH_CLOSE_UNAUTHORIZED)
            return

        user = await user_from_jwt_token(token.strip())
        if user is None or not getattr(user, 'is_authenticated', False):
            await self.close(code=WS_AUTH_CLOSE_UNAUTHORIZED)
            return

        self._auth_pending = False
        if self._auth_timeout_task is not None:
            self._auth_timeout_task.cancel()
            try:
                await self._auth_timeout_task
            except asyncio.CancelledError:
                pass
            self._auth_timeout_task = None

        self.user = user
        self.scope['user'] = user

        try:
            await self.on_authenticated(user)
        except Exception:
            logger.exception('Ошибка on_authenticated для WebSocket')
            await self.close(code=1011)
            return

        await self.send_json({'type': WS_AUTH_OK_TYPE})
