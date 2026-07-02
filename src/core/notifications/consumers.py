import logging

from src.core.cms.adp.consumers.base import JwtMessageAuthConsumer

logger = logging.getLogger('core.notifications')


class NotificationsConsumer(JwtMessageAuthConsumer):
    """Персональный канал доставки уведомлений пользователю.

    Подключение: `ws://<host>/ws/notifications/`, первое сообщение:
    `{ type: 'auth', token: '<JWT>' }`.

    Группа: `notifications_user_<user_id>`.
    Сервер шлёт клиенту события:
        { type: 'notification_new', notification: {...} }
    """

    group_name: str | None = None

    async def on_ws_authenticated(self):
        self.group_name = f'notifications_user_{self.ws_user.pk}'
        await self.channel_layer.group_add(self.group_name, self.channel_name)

    async def on_ws_disconnect(self, close_code):
        if self.group_name:
            await self.channel_layer.group_discard(self.group_name, self.channel_name)

    async def notification_new(self, event):
        await self.send_json({
            'type': 'notification_new',
            'notification': event['notification'],
        })
