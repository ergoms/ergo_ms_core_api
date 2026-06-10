import logging

from django.db import transaction

logger = logging.getLogger('core.notifications')


class EmailChannel:
    """Канал доставки по электронной почте.

    Решение об отправке принимает PreferenceResolver (галочка «По эл. почте»
    в панели настроек). Сама отправка асинхронная — через Celery-задачу,
    поставленную строго после commit транзакции dispatch
    (см. transaction.on_commit), иначе воркер может не увидеть запись.
    """

    name = 'email'

    def deliver(self, notification, *, created: bool) -> None:
        if not created:
            return  # повтор по idempotency_key — письмо уже ставилось

        from ..preferences import PreferenceResolver

        if not PreferenceResolver.is_enabled(
            notification.recipient_id,
            source_module=notification.source_module,
            event_key=notification.event_key,
            channel='email',
        ):
            return

        notification_id = notification.pk

        def _enqueue():
            try:
                from ..tasks import send_notification_email_task
                send_notification_email_task.delay(notification_id)
            except Exception:
                logger.exception(
                    'EmailChannel: не удалось поставить задачу отправки для notification=%s',
                    notification_id,
                )

        transaction.on_commit(_enqueue)
