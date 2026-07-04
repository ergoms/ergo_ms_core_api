import csv

from django.http import HttpResponse
from django.utils.dateparse import parse_datetime
from rest_framework import permissions, viewsets
from rest_framework.decorators import action
from rest_framework.pagination import PageNumberPagination
from rest_framework.response import Response

from src.core.settings.permissions import IsGlobalAdmin
from src.core.utils.mixins import SwaggerSafeMixin

from . import catalog
from .models import AuditEvent
from .serializers import AuditEventSerializer


class AuditPagination(PageNumberPagination):
    page_size = 50
    page_size_query_param = 'page_size'
    max_page_size = 200


class AuditEventViewSet(SwaggerSafeMixin, viewsets.ReadOnlyModelViewSet):
    """Единый журнал действий пользователей (только чтение).

    Доступен глобальному администратору. Фильтры: модуль, действие,
    инициатор, важность, период, организация, поиск по объекту/инициатору.
    """

    serializer_class = AuditEventSerializer
    permission_classes = [permissions.IsAuthenticated, IsGlobalAdmin]
    pagination_class = AuditPagination

    def _apply_filters(self, qs):
        params = self.request.query_params

        source_module = params.get('source_module')
        if source_module:
            qs = qs.filter(source_module=source_module)

        action_value = params.get('action')
        if action_value:
            qs = qs.filter(action=action_value)

        severity = params.get('severity')
        if severity:
            qs = qs.filter(severity=severity)

        actor_id = params.get('actor_id')
        if actor_id:
            try:
                qs = qs.filter(actor_id=int(actor_id))
            except (TypeError, ValueError):
                pass

        organization_id = params.get('organization_id')
        if organization_id:
            try:
                qs = qs.filter(organization_id=int(organization_id))
            except (TypeError, ValueError):
                pass

        date_from = params.get('date_from')
        if date_from:
            parsed = parse_datetime(date_from) or parse_datetime(f'{date_from}T00:00:00')
            if parsed is not None:
                qs = qs.filter(created_at__gte=parsed)

        date_to = params.get('date_to')
        if date_to:
            parsed = parse_datetime(date_to) or parse_datetime(f'{date_to}T23:59:59')
            if parsed is not None:
                qs = qs.filter(created_at__lte=parsed)

        search = (params.get('q') or '').strip()
        if search:
            from django.db.models import Q
            qs = qs.filter(
                Q(actor_label__icontains=search)
                | Q(entity_label__icontains=search)
                | Q(actor__username__icontains=search)
            )

        return qs

    def get_queryset(self):
        if self.is_swagger_fake_view():
            return AuditEvent.objects.none()
        qs = AuditEvent.objects.select_related('actor').all()
        return self._apply_filters(qs)

    @action(detail=False, methods=['get'], url_path='catalog')
    def catalog(self, request):
        """Справочник для UI: модули-источники и действия с подписями/иконками."""
        return Response({
            'modules': catalog.get_modules(),
            'actions': catalog.get_flat_actions(),
            'severities': [
                {'value': value, 'label': label}
                for value, label in AuditEvent.SEVERITY_CHOICES
            ],
        })

    @action(detail=False, methods=['get'], url_path='export')
    def export(self, request):
        """Экспорт отфильтрованного журнала в CSV."""
        qs = self.get_queryset()[:10000]
        catalog_data = catalog.get_catalog()

        response = HttpResponse(content_type='text/csv; charset=utf-8')
        response['Content-Disposition'] = 'attachment; filename="audit_log.csv"'
        response.write('\ufeff')  # BOM для корректных кириллических заголовков в Excel

        writer = csv.writer(response, delimiter=';')
        writer.writerow(['Время', 'Модуль', 'Действие', 'Важность', 'Инициатор', 'Объект', 'IP'])

        for event in qs:
            section = catalog_data.get(event.source_module or '')
            module_label = section['module_label'] if section else event.source_module
            spec = section['actions'].get(event.action) if section else None
            action_label = spec['label'] if spec else event.action
            writer.writerow([
                event.created_at.strftime('%d.%m.%Y %H:%M:%S'),
                module_label,
                action_label,
                event.get_severity_display(),
                event.actor_label,
                event.entity_label,
                event.ip_address or '',
            ])

        return response
