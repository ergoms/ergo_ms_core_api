import logging
from typing import Any

from django.contrib.auth import get_user_model
from django.db import transaction
from django.utils import timezone

from .channels_ import get_channels
from .models import Notification

logger = logging.getLogger('core.notifications')

User = get_user_model()


def _resolve_recipient(recipient: Any):
    """Принимает User-инстанс или PK; возвращает (user_id, ok)."""
    if recipient is None:
        return None, False
    if isinstance(recipient, User):
        return recipient.pk, True
    if hasattr(recipient, 'pk') and isinstance(recipient.pk, int):
        return recipient.pk, True
    if isinstance(recipient, int):
        return recipient, True
    return None, False


class NotificationService:
    """Точка входа для создания и доставки уведомлений.

    Используется внутри ядра и через ModuleBridge (`notifications.create`)
    из любых модулей. Сначала создаётся (или возвращается существующая по
    `idempotency_key`) запись Notification, затем по очереди вызываются все
    зарегистрированные каналы доставки.
    """

    @staticmethod
    @transaction.atomic
    def dispatch(
        *,
        recipient: Any,
        title: str,
        body: str = '',
        level: str = Notification.LEVEL_INFO,
        icon: str = '',
        source_module: str = '',
        event_key: str = '',
        link_url: str | None = None,
        route: dict | None = None,
        meta: dict | None = None,
        idempotency_key: str | None = None,
    ) -> Notification | None:
        recipient_id, ok = _resolve_recipient(recipient)
        if not ok:
            logger.warning('NotificationService.dispatch: некорректный recipient=%r', recipient)
            return None

        if not title or not isinstance(title, str):
            logger.warning('NotificationService.dispatch: пустой/некорректный title')
            return None

        defaults = {
            'title': title,
            'body': body or '',
            'level': level or Notification.LEVEL_INFO,
            'icon': icon or '',
            'source_module': source_module or '',
            'event_key': event_key or '',
            'link_url': link_url or '',
            'route': route,
            'meta': meta or {},
        }

        if idempotency_key:
            notification, created = Notification.objects.get_or_create(
                recipient_id=recipient_id,
                idempotency_key=idempotency_key,
                defaults=defaults,
            )
        else:
            notification = Notification.objects.create(
                recipient_id=recipient_id,
                idempotency_key=None,
                **defaults,
            )
            created = True

        for channel in get_channels().values():
            try:
                channel.deliver(notification, created=created)
            except Exception:
                logger.exception('Канал %s упал при доставке уведомления #%s',
                                 getattr(channel, 'name', channel), notification.pk)

        return notification

    @staticmethod
    def mark_read(notification_id: int, user) -> bool:
        try:
            notif = Notification.objects.get(pk=notification_id, recipient=user)
        except Notification.DoesNotExist:
            return False
        if not notif.is_read:
            notif.is_read = True
            notif.read_at = timezone.now()
            notif.save(update_fields=['is_read', 'read_at'])
        return True

    @staticmethod
    def mark_all_read(user) -> int:
        return Notification.objects.filter(recipient=user, is_read=False).update(
            is_read=True,
            read_at=timezone.now(),
        )

    @staticmethod
    def unread_count(user) -> int:
        return Notification.objects.filter(recipient=user, is_read=False).count()
