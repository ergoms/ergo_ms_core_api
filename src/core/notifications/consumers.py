import logging
from urllib.parse import parse_qs

from channels.db import database_sync_to_async
from channels.generic.websocket import AsyncJsonWebsocketConsumer
from django.contrib.auth import get_user_model

logger = logging.getLogger('core.notifications')

User = get_user_model()


class NotificationsConsumer(AsyncJsonWebsocketConsumer):
    """Персональный канал доставки уведомлений пользователю.

    Подключение: `ws://<host>/ws/notifications/?token=<JWT>`.
    Аутентификация:
        1) если AuthMiddlewareStack уже положил пользователя в scope —
           берём его (например, в браузере с Django-сессией);
        2) иначе валидируем JWT-токен из query string `?token=...`
           через rest_framework_simplejwt — основной путь работы фронта.

    Группа: `notifications_user_<user_id>`.
    Сервер шлёт клиенту события:
        { type: 'notification_new', notification: {...} }
    """

    group_name: str | None = None

    async def connect(self):
        user = self.scope.get('user')
        if not user or not getattr(user, 'is_authenticated', False):
            user = await self._authenticate_via_query()

        if not user or not getattr(user, 'is_authenticated', False):
            await self.close(code=4401)
            return

        self.scope['user'] = user
        self.group_name = f'notifications_user_{user.pk}'
        await self.channel_layer.group_add(self.group_name, self.channel_name)
        await self.accept()

    async def disconnect(self, close_code):
        if self.group_name:
            await self.channel_layer.group_discard(self.group_name, self.channel_name)

    async def receive_json(self, content, **kwargs):
        # Пользовательские входящие сообщения сейчас не обрабатываются;
        # клиент только слушает push.
        return

    async def notification_new(self, event):
        await self.send_json({
            'type': 'notification_new',
            'notification': event['notification'],
        })

    async def _authenticate_via_query(self):
        query = self.scope.get('query_string', b'') or b''
        try:
            params = parse_qs(query.decode('utf-8'))
        except Exception:
            return None
        token = (params.get('token') or [None])[0]
        if not token:
            return None
        return await self._user_from_jwt(token)

    @staticmethod
    @database_sync_to_async
    def _user_from_jwt(token: str):
        try:
            from rest_framework_simplejwt.tokens import UntypedToken
            from rest_framework_simplejwt.exceptions import InvalidToken, TokenError
        except Exception:
            logger.exception('rest_framework_simplejwt не установлен')
            return None

        try:
            validated = UntypedToken(token)
        except (InvalidToken, TokenError):
            return None
        except Exception:
            logger.exception('Не удалось разобрать JWT для WebSocket')
            return None

        user_id = validated.get('user_id')
        if not user_id:
            return None
        try:
            return User.objects.get(pk=user_id)
        except User.DoesNotExist:
            return None
