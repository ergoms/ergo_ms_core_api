from django.db import models
from rest_framework import viewsets, status
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated, AllowAny
from django_filters.rest_framework import DjangoFilterBackend
from rest_framework import filters
import logging

from src.core.utils.mixins import SwaggerSafeMixin

logger = logging.getLogger(__name__)

from .models import (
    LcpModule, LcpPage, LcpComponentCategory, LcpComponentTemplate,
    LcpDataSource, LcpDatabaseTable, LcpAction, LcpVariable, LcpAuditLog
)
from .serializers import (
    LcpModuleSerializer, LcpModuleListSerializer,
    LcpPageSerializer, LcpPageListSerializer,
    LcpComponentCategorySerializer,
    LcpComponentTemplateSerializer, LcpComponentTemplateListSerializer,
    LcpDataSourceSerializer, LcpDatabaseTableSerializer,
    LcpActionSerializer, LcpVariableSerializer, LcpAuditLogSerializer
)


class LcpModuleViewSet(SwaggerSafeMixin, viewsets.ModelViewSet):
    """ViewSet для управления LCP модулями"""
    queryset = LcpModule.objects.all()
    serializer_class = LcpModuleSerializer
    lookup_field = 'slug'
    filter_backends = [DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter]
    search_fields = ['name', 'description']
    ordering_fields = ['menu_order', 'name', 'created_at']
    ordering = ['menu_order', 'name']
    
    def get_permissions(self):
        if self.action in ['list', 'retrieve']:
            return [AllowAny()]
        return [IsAuthenticated()]
    
    def get_serializer_class(self):
        if self.action == 'list':
            return LcpModuleListSerializer
        return LcpModuleSerializer
    
    def perform_create(self, serializer):
        serializer.save(created_by=self.request.user)
    
    def perform_destroy(self, instance):
        """Переопределяем destroy для логирования"""
        try:
            logger.info(f'Удаление модуля {instance.slug} (ID: {instance.id})')
            instance.delete()
            logger.info(f'Модуль {instance.slug} успешно удалён')
        except Exception as e:
            logger.error(f'Ошибка при удалении модуля {instance.slug}: {str(e)}', exc_info=True)
            raise
    
    @action(detail=True, methods=['get'])
    def pages(self, request, slug=None):
        """Получить страницы модуля"""
        module = self.get_object()
        pages = module.pages.all()
        serializer = LcpPageListSerializer(pages, many=True)
        return Response(serializer.data)
    
    @action(detail=True, methods=['get'])
    def full(self, request, slug=None):
        """Получить модуль со всеми связанными данными"""
        module = self.get_object()
        data = LcpModuleSerializer(module).data
        data['pages'] = LcpPageListSerializer(module.pages.all(), many=True).data
        data['data_sources'] = LcpDataSourceSerializer(module.data_sources.all(), many=True).data
        data['actions'] = LcpActionSerializer(module.actions.all(), many=True).data
        data['variables'] = LcpVariableSerializer(module.variables.all(), many=True).data
        return Response(data)


class LcpPageViewSet(SwaggerSafeMixin, viewsets.ModelViewSet):
    """ViewSet для управления страницами"""
    queryset = LcpPage.objects.select_related('module')
    serializer_class = LcpPageSerializer
    filter_backends = [DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter]
    filterset_fields = ['module', 'is_draft', 'is_template', 'is_homepage']
    search_fields = ['name', 'slug']
    ordering_fields = ['menu_order', 'name', 'updated_at']
    ordering = ['menu_order', 'name']
    
    def get_permissions(self):
        if self.action in ['list', 'retrieve', 'by_path']:
            return [AllowAny()]
        return [IsAuthenticated()]
    
    def get_serializer_class(self):
        if self.action == 'list':
            return LcpPageListSerializer
        return LcpPageSerializer
    
    def perform_create(self, serializer):
        serializer.save(created_by=self.request.user)
    
    @action(detail=False, methods=['get'], url_path='by-path')
    def by_path(self, request):
        """Получить страницу по полному пути"""
        module_slug = request.query_params.get('module')
        page_slug = request.query_params.get('page')
        
        if not module_slug:
            return Response({'detail': 'module параметр обязателен'}, status=400)
        
        try:
            if page_slug:
                page = LcpPage.objects.get(module__slug=module_slug, slug=page_slug)
            else:
                # Возвращаем homepage модуля
                page = LcpPage.objects.get(module__slug=module_slug, is_homepage=True)
        except LcpPage.DoesNotExist:
            return Response({'detail': 'Страница не найдена'}, status=404)
        
        serializer = LcpPageSerializer(page)
        return Response(serializer.data)
    
    @action(detail=True, methods=['post'])
    def duplicate(self, request, pk=None):
        """Дублировать страницу"""
        page = self.get_object()
        new_page = LcpPage.objects.create(
            name=f'{page.name} (копия)',
            slug=f'{page.slug}-copy',
            module=page.module,
            component_tree=page.component_tree,
            settings=page.settings,
            variables=page.variables,
            data_sources=page.data_sources,
            breakpoints=page.breakpoints,
            is_draft=True,
            icon=page.icon,
            created_by=request.user
        )
        serializer = LcpPageSerializer(new_page)
        return Response(serializer.data, status=status.HTTP_201_CREATED)
    
    @action(detail=True, methods=['post'])
    def make_template(self, request, pk=None):
        """Сделать страницу шаблоном"""
        page = self.get_object()
        page.is_template = True
        page.save()
        return Response({'status': 'ok'})


class LcpComponentCategoryViewSet(viewsets.ModelViewSet):
    """ViewSet для категорий компонентов"""
    queryset = LcpComponentCategory.objects.all()
    serializer_class = LcpComponentCategorySerializer
    lookup_field = 'slug'
    
    def get_permissions(self):
        if self.action in ['list', 'retrieve']:
            return [AllowAny()]
        return [IsAuthenticated()]


class LcpComponentTemplateViewSet(SwaggerSafeMixin, viewsets.ModelViewSet):
    """ViewSet для шаблонов компонентов"""
    queryset = LcpComponentTemplate.objects.select_related('category', 'module')
    serializer_class = LcpComponentTemplateSerializer
    filter_backends = [DjangoFilterBackend, filters.SearchFilter]
    filterset_fields = ['category', 'component_type', 'is_global', 'is_system', 'module']
    search_fields = ['name', 'description']
    
    def get_permissions(self):
        if self.action in ['list', 'retrieve', 'palette']:
            return [AllowAny()]
        return [IsAuthenticated()]
    
    def get_serializer_class(self):
        if self.action in ['list', 'palette']:
            return LcpComponentTemplateListSerializer
        return LcpComponentTemplateSerializer
    
    def perform_create(self, serializer):
        serializer.save(created_by=self.request.user)
    
    @action(detail=False, methods=['get'])
    def palette(self, request):
        """Компоненты для палитры редактора"""
        module_id = request.query_params.get('module')
        
        # Глобальные + системные + модульные
        qs = self.queryset.filter(is_active=True)
        if module_id:
            qs = qs.filter(
                models.Q(is_global=True) |
                models.Q(is_system=True) |
                models.Q(module_id=module_id)
            )
        else:
            qs = qs.filter(models.Q(is_global=True) | models.Q(is_system=True))
        
        # Группировка по категориям
        categories = LcpComponentCategory.objects.all()
        result = []
        for cat in categories:
            components = qs.filter(category=cat)
            if components.exists():
                result.append({
                    'category': LcpComponentCategorySerializer(cat).data,
                    'components': LcpComponentTemplateListSerializer(components, many=True).data
                })
        
        return Response(result)


class LcpDataSourceViewSet(SwaggerSafeMixin, viewsets.ModelViewSet):
    """ViewSet для источников данных"""
    queryset = LcpDataSource.objects.select_related('module')
    serializer_class = LcpDataSourceSerializer
    filter_backends = [DjangoFilterBackend, filters.SearchFilter]
    filterset_fields = ['module', 'source_type', 'is_active']
    search_fields = ['name', 'description']
    
    def get_permissions(self):
        if self.action in ['list', 'retrieve']:
            return [AllowAny()]
        return [IsAuthenticated()]
    
    def perform_create(self, serializer):
        serializer.save(created_by=self.request.user)
    
    @action(detail=True, methods=['post'])
    def execute(self, request, pk=None):
        """Выполнить запрос источника данных"""
        data_source = self.get_object()
        params = request.data.get('params', {})
        
        # TODO: Реализовать выполнение запросов
        # В зависимости от source_type вызывать соответствующий сервис
        
        return Response({'status': 'not_implemented'}, status=501)


class LcpDatabaseTableViewSet(SwaggerSafeMixin, viewsets.ModelViewSet):
    """ViewSet для таблиц БД"""
    queryset = LcpDatabaseTable.objects.select_related('module')
    serializer_class = LcpDatabaseTableSerializer
    filter_backends = [DjangoFilterBackend]
    filterset_fields = ['module', 'is_migrated']
    
    def get_permissions(self):
        if self.action in ['list', 'retrieve']:
            return [AllowAny()]
        return [IsAuthenticated()]
    
    def perform_create(self, serializer):
        serializer.save(created_by=self.request.user)
    
    @action(detail=True, methods=['post'])
    def generate_migration(self, request, pk=None):
        """Сгенерировать миграцию для таблицы"""
        table = self.get_object()
        
        # TODO: Реализовать генерацию миграций
        
        return Response({'status': 'not_implemented'}, status=501)


class LcpActionViewSet(SwaggerSafeMixin, viewsets.ModelViewSet):
    """ViewSet для действий"""
    queryset = LcpAction.objects.select_related('module')
    serializer_class = LcpActionSerializer
    filter_backends = [DjangoFilterBackend, filters.SearchFilter]
    filterset_fields = ['module', 'action_type', 'is_active']
    search_fields = ['name', 'description']
    
    def get_permissions(self):
        if self.action in ['list', 'retrieve']:
            return [AllowAny()]
        return [IsAuthenticated()]
    
    def perform_create(self, serializer):
        serializer.save(created_by=self.request.user)


class LcpVariableViewSet(SwaggerSafeMixin, viewsets.ModelViewSet):
    """ViewSet для переменных"""
    queryset = LcpVariable.objects.select_related('module')
    serializer_class = LcpVariableSerializer
    filter_backends = [DjangoFilterBackend]
    filterset_fields = ['module', 'scope', 'var_type']
    
    def get_permissions(self):
        if self.action in ['list', 'retrieve']:
            return [AllowAny()]
        return [IsAuthenticated()]


class LcpAuditLogViewSet(viewsets.ReadOnlyModelViewSet):
    """ViewSet для просмотра аудита (только чтение)"""
    queryset = LcpAuditLog.objects.select_related('user', 'content_type')
    serializer_class = LcpAuditLogSerializer
    filter_backends = [DjangoFilterBackend, filters.OrderingFilter]
    filterset_fields = ['content_type', 'object_id', 'action', 'user']
    ordering_fields = ['timestamp']
    ordering = ['-timestamp']
    permission_classes = [IsAuthenticated]

