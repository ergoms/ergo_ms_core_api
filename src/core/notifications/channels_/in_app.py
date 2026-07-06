import logging

from src.core.realtime.hub import RealtimeHub
from src.core.realtime.topics import notifications_user_group, notifications_user_topic

logger = logging.getLogger('core.notifications')


class InAppChannel:
    """Доставка уведомления внутрь приложения.

    Сама запись в БД создаётся в NotificationService (до вызова канала).
    Этот канал отвечает за push в персональную группу пользователя (WS / SSE).
    Если канальный слой недоступен — тихо логируем, запись в БД остаётся
    и будет показана при следующем HTTP-запросе или подключении stream.
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
            payload = NotificationSerializer(notification).data
            user_id = notification.recipient_id
            RealtimeHub.publish(
                group=notifications_user_group(user_id),
                topic=notifications_user_topic(user_id),
                event_type='notification_new',
                payload=payload,
            )
        except Exception:
            logger.exception('Не удалось отправить in-app уведомление через realtime')
