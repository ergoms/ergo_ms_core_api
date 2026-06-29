import logging

from channels.generic.websocket import AsyncJsonWebsocketConsumer

from src.core.cms.adp.ws_auth import authenticate_ws_scope

logger = logging.getLogger('core.notifications')


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
        user = await authenticate_ws_scope(self.scope)
        if user is None or not getattr(user, 'is_authenticated', False):
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
        return

    async def notification_new(self, event):
        await self.send_json({
            'type': 'notification_new',
            'notification': event['notification'],
        })
