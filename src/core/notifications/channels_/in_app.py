import logging

from asgiref.sync import async_to_sync
from channels.layers import get_channel_layer

logger = logging.getLogger('core.notifications')


class InAppChannel:
    """Доставка уведомления внутрь приложения.

    Сама запись в БД создаётся в NotificationService (до вызова канала).
    Этот канал отвечает за push в персональную WebSocket-группу пользователя.
    Если канальный слой недоступен — тихо логируем, запись в БД остаётся
    и будет показана при следующем HTTP-запросе или подключении WS.
    """

    name = 'in_app'

    def deliver(self, notification, *, created: bool) -> None:
        if not created:
            return
        if not notification.in_app_visible:
            return

        try:
            from ..serializers import NotificationSerializer
        except Exception:
            logger.exception('NotificationSerializer недоступен')
            return

        try:
            channel_layer = get_channel_layer()
            if channel_layer is None:
                return
            group_name = f'notifications_user_{notification.recipient_id}'
            payload = NotificationSerializer(notification).data
            async_to_sync(channel_layer.group_send)(
                group_name,
                {
                    'type': 'notification_new',
                    'notification': payload,
                },
            )
        except Exception:
            logger.exception('Не удалось отправить in-app уведомление через WebSocket')
