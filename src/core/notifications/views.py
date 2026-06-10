from datetime import timedelta

from django.db.models import Q
from django.utils import timezone
from rest_framework import permissions, viewsets
from rest_framework.decorators import action
from rest_framework.response import Response

from src.core.utils.mixins import SwaggerSafeMixin

from .models import Notification
from .preferences import PreferencePanelService
from .serializers import NotificationSerializer
from .services import NotificationService


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

    def get_queryset(self):
        if self.is_swagger_fake_view():
            return Notification.objects.none()

        qs = Notification.objects.filter(recipient=self.request.user, in_app_visible=True)

        is_read = self.request.query_params.get('is_read')
        if is_read is not None:
            value = is_read.lower() in ('1', 'true', 'yes')
            qs = qs.filter(is_read=value)

        source_module = self.request.query_params.get('source_module')
        if source_module:
            qs = qs.filter(source_module=source_module)

        if self.request.query_params.get('inbox') == 'sidebar':
            week_ago = timezone.now() - timedelta(days=7)
            qs = qs.filter(
                Q(is_read=False)
                | Q(is_read=True, read_at__gte=week_ago)
                | Q(is_read=True, read_at__isnull=True, created_at__gte=week_ago)
            )

        return qs

    @action(detail=False, methods=['get'], url_path='unread_count')
    def unread_count(self, request):
        return Response({'count': NotificationService.unread_count(request.user)})

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
        updated = NotificationService.mark_all_read(request.user)
        return Response({
            'success': True,
            'updated': updated,
            'unread_count': 0,
        })

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
