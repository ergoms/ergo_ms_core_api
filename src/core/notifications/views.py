from datetime import timedelta

from django.db.models import Q
from django.utils import timezone
from django.utils.dateparse import parse_datetime
from rest_framework import permissions, viewsets
from rest_framework.decorators import action
from rest_framework.pagination import LimitOffsetPagination
from rest_framework.response import Response

from src.core.utils.mixins import SwaggerSafeMixin

from src.core.realtime.envelope import build_envelope
from src.core.realtime.polling import apply_after_id
from src.core.realtime.topics import notifications_user_topic

from .models import Notification
from .preferences import PreferencePanelService
from .serializers import NotificationSerializer
from .services import NotificationService


class NotificationPagination(LimitOffsetPagination):
    default_limit = 30
    max_limit = 100


class NotificationViewSet(SwaggerSafeMixin, viewsets.ReadOnlyModelViewSet):
    """Инбокс уведомлений текущего пользователя.

    Список + действия:
        GET    /notifications/                   список
        GET    /notifications/unread_count/      счётчик непрочитанных
        POST   /notifications/{id}/mark_read/    отметить прочитанным
        POST   /notifications/mark_all_read/     отметить все прочитанными
    """

    serializer_class = NotificationSerializer
    permission_classes = [permissions.IsAuthenticated]
    pagination_class = NotificationPagination

    def get_queryset(self):
        if self.is_swagger_fake_view():
            return Notification.objects.none()

        qs = Notification.objects.filter(
            recipient=self.request.user,
            in_app_visible=True,
            deleted_at__isnull=True,
        )

        archived = self.request.query_params.get('archived')
        if archived is not None and archived.lower() in ('1', 'true', 'yes'):
            qs = qs.filter(archived_at__isnull=False)
        else:
            qs = qs.filter(archived_at__isnull=True)

        is_read = self.request.query_params.get('is_read')
        if is_read is not None:
            value = is_read.lower() in ('1', 'true', 'yes')
            qs = qs.filter(is_read=value)

        source_module = self.request.query_params.get('source_module')
        if source_module:
            qs = qs.filter(source_module=source_module)

        if self.request.query_params.get('inbox') == 'sidebar':
            week_ago = timezone.now() - timedelta(days=7)
            qs = qs.filter(sidebar_hidden_at__isnull=True).filter(
                Q(is_read=False)
                | Q(is_read=True, read_at__gte=week_ago)
                | Q(is_read=True, read_at__isnull=True, created_at__gte=week_ago)
            )

        created_after = self.request.query_params.get('created_after')
        if created_after:
            parsed = parse_datetime(created_after.strip())
            if parsed is not None:
                if timezone.is_naive(parsed):
                    parsed = timezone.make_aware(parsed, timezone.get_current_timezone())
                qs = qs.filter(created_at__gt=parsed)

        qs = apply_after_id(qs, self.request)

        return qs

    def _serialize(self, notification):
        return NotificationSerializer(notification).data

    @action(detail=False, methods=['get'], url_path='unread_count')
    def unread_count(self, request):
        return Response({'count': NotificationService.unread_count(request.user)})

    @action(detail=False, methods=['get'], url_path='source_modules')
    def source_modules(self, request):
        modules = (
            Notification.objects.filter(
                recipient=request.user,
                in_app_visible=True,
                deleted_at__isnull=True,
            )
            .exclude(source_module='')
            .values_list('source_module', flat=True)
            .distinct()
            .order_by('source_module')
        )
        return Response({'results': list(modules)})

    @action(detail=True, methods=['post'], url_path='mark_read')
    def mark_read(self, request, pk=None):
        ok = NotificationService.mark_read(pk, request.user)
        if not ok:
            return Response({'success': False}, status=404)
        return Response({
            'success': True,
            'unread_count': NotificationService.unread_count(request.user),
        })

    @action(detail=False, methods=['post'], url_path='mark_all_read')
    def mark_all_read(self, request):
        source_module = (request.data.get('source_module') or '').strip() or None
        updated = NotificationService.mark_all_read(
            request.user,
            source_module=source_module,
        )
        return Response({
            'success': True,
            'updated': updated,
            'unread_count': NotificationService.unread_count(request.user),
        })

    @action(detail=True, methods=['post'], url_path='archive')
    def archive(self, request, pk=None):
        notif = NotificationService.archive(pk, request.user)
        if notif is None:
            return Response({'success': False}, status=404)
        return Response({
            'success': True,
            'notification': self._serialize(notif),
            'unread_count': NotificationService.unread_count(request.user),
        })

    @action(detail=True, methods=['post'], url_path='unarchive')
    def unarchive(self, request, pk=None):
        notif = NotificationService.unarchive(pk, request.user)
        if notif is None:
            return Response({'success': False}, status=404)
        return Response({
            'success': True,
            'notification': self._serialize(notif),
            'unread_count': NotificationService.unread_count(request.user),
        })

    @action(detail=True, methods=['post'], url_path='hide_from_sidebar')
    def hide_from_sidebar(self, request, pk=None):
        notif = NotificationService.hide_from_sidebar(pk, request.user)
        if notif is None:
            return Response({'success': False}, status=404)
        return Response({
            'success': True,
            'notification': self._serialize(notif),
            'unread_count': NotificationService.unread_count(request.user),
        })

    @action(detail=True, methods=['post', 'delete'], url_path='delete')
    def soft_delete(self, request, pk=None):
        ok = NotificationService.soft_delete(pk, request.user)
        if not ok:
            return Response({'success': False}, status=404)
        return Response({
            'success': True,
            'unread_count': NotificationService.unread_count(request.user),
        })

    @action(detail=True, methods=['post'], url_path='execute_action')
    def execute_action(self, request, pk=None):
        action_id = (request.data.get('action_id') or '').strip()
        if not action_id:
            return Response({'success': False, 'error': 'action_id_required'}, status=400)

        result = NotificationService.execute_action(pk, request.user, action_id)
        if result.get('error') == 'not_found':
            return Response({'success': False, 'error': 'not_found'}, status=404)

        notification = result.pop('notification', None)
        if notification is not None:
            result['envelope'] = build_envelope(
                topic=notifications_user_topic(request.user.pk),
                event_type='notification_updated',
                payload=NotificationSerializer(notification).data,
            )
        return Response(result, status=200 if result.get('success') else 400)

    @action(detail=False, methods=['get', 'patch'], url_path='preferences')
    def preferences(self, request):
        """Настройки уведомлений текущего пользователя.

        GET — секции каталога (модули/категории/события) с эффективными
        значениями каналов + глобальные master-switch.
        PATCH — batch-изменения: {'global': {channel: bool}, 'items': [
            {'source_module', 'event_key', 'channel', 'enabled'}]}.
        """
        if request.method == 'GET':
            return Response(PreferencePanelService.build_sections(request.user))

        payload = request.data if isinstance(request.data, dict) else {}
        updated = PreferencePanelService.apply_patch(request.user, payload)
        return Response({
            'success': True,
            'updated': updated,
            'global': PreferencePanelService.get_global_switches(request.user.pk),
        })
