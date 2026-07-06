import logging

from src.core.cms.adp.consumers.base import JwtMessageAuthConsumer
from src.core.realtime.consumer_mixin import RealtimeEnvelopeConsumerMixin
from src.core.realtime.topics import notifications_user_group

logger = logging.getLogger('core.notifications')


class NotificationsConsumer(RealtimeEnvelopeConsumerMixin, JwtMessageAuthConsumer):
    """Персональный канал доставки уведомлений пользователю.

    Подключение: `ws://<host>/ws/notifications/`, первое сообщение — envelope
    `{ type: 'ws_auth', payload: { token: '<JWT>' } }`.

    Группа: `notifications_user_<user_id>`.
    Клиенту отправляется envelope: `{ v, id, topic, type, payload, ts }`.
    """

    group_name: str | None = None

    async def on_ws_authenticated(self):
        self.group_name = notifications_user_group(self.ws_user.pk)
        await self.channel_layer.group_add(self.group_name, self.channel_name)

    async def on_ws_disconnect(self, close_code):
        if self.group_name:
            await self.channel_layer.group_discard(self.group_name, self.channel_name)
