import logging
from typing import Any

from django.contrib.auth import get_user_model
from django.db import transaction
from django.utils import timezone

from src.core.integrations import bridge

from .channels_ import get_channels
from .models import Notification
from .navigation_validation import sanitize_notification_navigation, validate_notification_navigation
from .preferences import PreferenceResolver
from .unread_cache import (
    get_cached_unread_count,
    invalidate_unread_count_cache,
    set_cached_unread_count,
)

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
        actions: list | None = None,
        idempotency_key: str | None = None,
    ) -> Notification | None:
        recipient_id, ok = _resolve_recipient(recipient)
        if not ok:
            logger.warning('NotificationService.dispatch: некорректный recipient=%r', recipient)
            return None

        if not title or not isinstance(title, str):
            logger.warning('NotificationService.dispatch: пустой/некорректный title')
            return None

        nav_errors = validate_notification_navigation(link_url=link_url, route=route)
        if nav_errors:
            logger.warning(
                'NotificationService.dispatch: навигация санитизирована (%s)',
                '; '.join(nav_errors),
            )
        link_url, route = sanitize_notification_navigation(link_url=link_url, route=route)

        enabled_channels = PreferenceResolver.get_enabled_channels(
            recipient_id,
            source_module=source_module or '',
            event_key=event_key or '',
        )
        if not any(enabled_channels.values()):
            logger.debug(
                'NotificationService.dispatch: подавлено настройками user=%s %s.%s',
                recipient_id, source_module, event_key,
            )
            return None

        action_list = actions if isinstance(actions, list) else []
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
            'actions': action_list,
            'actions_state': 'pending' if action_list else None,
            # email-only уведомление хранит данные для письма, но скрыто из inbox
            'in_app_visible': enabled_channels.get('in_app', True),
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

        if notification.in_app_visible:
            invalidate_unread_count_cache(recipient_id)

        return notification

    @staticmethod
    def mark_read(notification_id: int, user) -> bool:
        try:
            notif = Notification.objects.get(
                pk=notification_id,
                recipient=user,
                deleted_at__isnull=True,
            )
        except Notification.DoesNotExist:
            return False
        if not notif.is_read:
            notif.is_read = True
            notif.read_at = timezone.now()
            notif.save(update_fields=['is_read', 'read_at'])
            invalidate_unread_count_cache(user.pk)
        return True

    @staticmethod
    def mark_all_read(user, *, source_module: str | None = None) -> int:
        qs = Notification.objects.filter(
            recipient=user,
            is_read=False,
            in_app_visible=True,
            deleted_at__isnull=True,
            archived_at__isnull=True,
        )
        if source_module:
            qs = qs.filter(source_module=source_module)
        updated = qs.update(
            is_read=True,
            read_at=timezone.now(),
        )
        if updated:
            invalidate_unread_count_cache(user.pk)
        return updated

    @staticmethod
    def unread_count(user) -> int:
        user_id = getattr(user, 'pk', None)
        if user_id is None:
            return 0

        cached = get_cached_unread_count(user_id)
        if cached is not None:
            return cached

        count = Notification.objects.filter(
            recipient=user,
            is_read=False,
            in_app_visible=True,
            deleted_at__isnull=True,
            archived_at__isnull=True,
        ).count()
        set_cached_unread_count(user_id, count)
        return count

    @staticmethod
    def _get_owned(notification_id: int, user) -> Notification | None:
        try:
            return Notification.objects.get(
                pk=notification_id,
                recipient=user,
                deleted_at__isnull=True,
            )
        except Notification.DoesNotExist:
            return None

    @staticmethod
    def archive(notification_id: int, user) -> Notification | None:
        notif = NotificationService._get_owned(notification_id, user)
        if notif is None:
            return None
        if notif.archived_at is None:
            notif.archived_at = timezone.now()
            if not notif.is_read:
                notif.is_read = True
                notif.read_at = notif.archived_at
                notif.save(update_fields=['archived_at', 'is_read', 'read_at'])
                invalidate_unread_count_cache(user.pk)
            else:
                notif.save(update_fields=['archived_at'])
        return notif

    @staticmethod
    def unarchive(notification_id: int, user) -> Notification | None:
        notif = NotificationService._get_owned(notification_id, user)
        if notif is None:
            return None
        if notif.archived_at is not None:
            notif.archived_at = None
            notif.save(update_fields=['archived_at'])
        return notif

    @staticmethod
    def hide_from_sidebar(notification_id: int, user) -> Notification | None:
        notif = NotificationService._get_owned(notification_id, user)
        if notif is None:
            return None
        if notif.sidebar_hidden_at is None:
            now = timezone.now()
            notif.sidebar_hidden_at = now
            update_fields = ['sidebar_hidden_at']
            if not notif.is_read:
                notif.is_read = True
                notif.read_at = now
                update_fields.extend(['is_read', 'read_at'])
                notif.save(update_fields=update_fields)
                invalidate_unread_count_cache(user.pk)
            else:
                notif.save(update_fields=update_fields)
        return notif

    @staticmethod
    def soft_delete(notification_id: int, user) -> bool:
        notif = NotificationService._get_owned(notification_id, user)
        if notif is None:
            return False
        was_unread = not notif.is_read and notif.archived_at is None
        notif.deleted_at = timezone.now()
        if not notif.is_read:
            notif.is_read = True
            notif.read_at = notif.deleted_at
            notif.save(update_fields=['deleted_at', 'is_read', 'read_at'])
        else:
            notif.save(update_fields=['deleted_at'])
        if was_unread:
            invalidate_unread_count_cache(user.pk)
        return True

    @staticmethod
    @transaction.atomic
    def execute_action(notification_id: int, user, action_id: str) -> dict:
        """Выполнить интерактивное действие уведомления через ModuleBridge."""
        try:
            notification = Notification.objects.select_for_update().get(
                pk=notification_id,
                recipient=user,
                in_app_visible=True,
                deleted_at__isnull=True,
            )
        except Notification.DoesNotExist:
            return {'success': False, 'error': 'not_found'}

        if notification.actions_state != 'pending':
            return {'success': False, 'error': 'not_pending'}

        action_def = None
        for item in notification.actions or []:
            if isinstance(item, dict) and item.get('id') == action_id:
                action_def = item
                break
        if not action_def:
            return {'success': False, 'error': 'invalid_action'}

        handler = action_def.get('handler') or ''
        if not handler or not bridge.has(handler):
            logger.warning(
                'NotificationService.execute_action: handler %r не зарегистрирован',
                handler,
            )
            return {'success': False, 'error': 'handler_unavailable'}

        try:
            result = bridge.call(
                handler,
                notification=notification,
                action_id=action_id,
                user=user,
            )
        except Exception:
            logger.exception(
                'NotificationService.execute_action: handler %s упал для #%s',
                handler,
                notification_id,
            )
            return {'success': False, 'error': 'handler_failed'}

        if not isinstance(result, dict) or not result.get('success'):
            return {
                'success': False,
                'error': result.get('error', 'handler_rejected') if isinstance(result, dict) else 'handler_rejected',
                'message': result.get('message', '') if isinstance(result, dict) else '',
            }

        now = timezone.now()
        update_fields = [
            'actions_state',
            'resolved_action_id',
            'resolved_at',
            'is_read',
            'read_at',
        ]
        notification.actions_state = 'resolved'
        notification.resolved_action_id = action_id
        notification.resolved_at = now
        notification.is_read = True
        notification.read_at = now

        update_payload = result.get('update') if isinstance(result.get('update'), dict) else {}
        if update_payload.get('body') is not None:
            notification.body = update_payload['body']
            update_fields.append('body')
        if update_payload.get('level'):
            notification.level = update_payload['level']
            update_fields.append('level')

        notification.save(update_fields=update_fields)
        invalidate_unread_count_cache(user.pk)

        return {
            'success': True,
            'message': result.get('message', ''),
            'notification': notification,
            'unread_count': NotificationService.unread_count(user),
        }
