import os
import re
import json
import logging
from django.utils import timezone
from rest_framework.response import Response
from rest_framework import viewsets, status
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated, AllowAny
from django.http import HttpResponse

from .permissions import IsGlobalAdmin
from src.core.utils.mixins import MediaApiFileMixin, read_storage_file_bytes
from src.core.audit.mixin import AuditedModelMixin

from .models import *
from .serializers import *


logger = logging.getLogger(__name__)


def _safe_content_disposition_filename(name):
    """Санитизирует имя файла для заголовка Content-Disposition (защита от response splitting)."""
    if name is None:
        return 'download'
    s = re.sub(r'[\x00-\x1f\x7f"\\\r\n]', '', str(name).strip())
    s = s[:200] if len(s) > 200 else s
    return s or 'download'


class _ThemeImportMixin(MediaApiFileMixin):
    """Чтение JSON-темы из прямой загрузки или из пути media_api."""

    def _read_theme_json(self, request):
        file, file_path = self.get_file_or_path('file')
        if file_path:
            return read_storage_file_bytes(file_path).decode('utf-8')
        if file:
            return file.read().decode('utf-8')
        return None


class _SettingsAuditMixin(AuditedModelMixin):
    """Изменения настроек-синглтонов пишутся единым действием settings.changed."""
    audit_module = 'core.settings'
    audit_severity = 'security'
    audit_action_map = {'create': 'settings.changed', 'update': 'settings.changed'}


class SecuritySettingsViewSet(_SettingsAuditMixin, viewsets.ModelViewSet):
    queryset = SecuritySettings.objects.all()
    serializer_class = SecuritySettingsSerializer
    permission_classes = [IsAuthenticated, IsGlobalAdmin]

class MediaSettingsViewSet(_SettingsAuditMixin, viewsets.ModelViewSet):
    queryset = MediaSettings.objects.all()
    serializer_class = MediaSettingsSerializer
    permission_classes = [IsAuthenticated, IsGlobalAdmin]

class PermalinkSettingsViewSet(_SettingsAuditMixin, viewsets.ModelViewSet):
    queryset = PermalinkSettings.objects.all()
    serializer_class = PermalinkSettingsSerializer
    permission_classes = [IsAuthenticated, IsGlobalAdmin]

class EmailSettingsViewSet(_SettingsAuditMixin, viewsets.ModelViewSet):
    queryset = EmailSettings.objects.all()
    serializer_class = EmailSettingsSerializer
    permission_classes = [IsAuthenticated, IsGlobalAdmin]

class UserAvatarViewSet(MediaApiFileMixin, viewsets.ModelViewSet):
    queryset = UserAvatar.objects.all()
    serializer_class = UserAvatarSerializer
    permission_classes = [IsAuthenticated]
    
    def get_serializer_class(self):
        """Используем легковесный сериализатор для списка"""
        if self.action == 'list':
            from .serializers import UserAvatarListSerializer
            return UserAvatarListSerializer
        return UserAvatarSerializer
    
    def get_queryset(self):
        if getattr(self, 'swagger_fake_view', False):
            return UserAvatar.objects.none()
        if not self.request.user.is_authenticated:
            return UserAvatar.objects.none()
        return UserAvatar.objects.filter(user=self.request.user)
    
    def perform_create(self, serializer):
        if self.request.user.is_authenticated:
            UserAvatar.objects.filter(user=self.request.user).delete()
            if self.request.data.get('image_path') or self.request.FILES.get('image'):
                self.get_file_or_path('image')
            serializer.save(user=self.request.user)
    
    @action(detail=False, methods=['delete'], url_path='current')
    def delete_current(self, request):
        """Удалить аватар текущего пользователя"""
        if not request.user.is_authenticated:
            return Response(
                {'error': 'Пользователь не аутентифицирован'},
                status=status.HTTP_401_UNAUTHORIZED
            )
        
        avatar = UserAvatar.objects.filter(user=request.user).first()
        if avatar:
            avatar.delete()
            return Response(status=status.HTTP_204_NO_CONTENT)
        return Response(
            {'detail': 'Аватар не найден'},
            status=status.HTTP_404_NOT_FOUND
        )

class ThemeViewSet(AuditedModelMixin, _ThemeImportMixin, viewsets.ModelViewSet):
    """ViewSet для управления темами оформления"""
    queryset = Theme.objects.all()
    serializer_class = ThemeSerializer
    audit_module = 'core.settings'
    audit_entity_type = 'theme'
    audit_action_map = {'create': 'theme.created', 'update': 'theme.updated', 'destroy': 'theme.deleted'}

    def get_permissions(self):
        if self.action == 'get_active_theme':
            return [AllowAny()]
        if self.action in ('list', 'retrieve'):
            return [IsAuthenticated()]
        return [IsAuthenticated(), IsGlobalAdmin()]
    
    def get_queryset(self):
        queryset = Theme.objects.all()
        # Фильтр по базовой теме
        base_theme = self.request.query_params.get('base_theme')
        if base_theme:
            queryset = queryset.filter(base_theme=base_theme)
        # Фильтр только активных
        is_active = self.request.query_params.get('is_active')
        if is_active is not None:
            queryset = queryset.filter(is_active=is_active == 'true')
        return queryset
    
    def destroy(self, request, *args, **kwargs):
        """Запрет удаления системных тем"""
        instance = self.get_object()
        if instance.is_system:
            return Response(
                {'error': 'Нельзя удалить системную тему'},
                status=status.HTTP_403_FORBIDDEN
            )
        return super().destroy(request, *args, **kwargs)
    
    @action(detail=False, methods=['get'], url_path='active')
    def get_active_theme(self, request):
        """Получить активную тему"""
        active_theme = Theme.objects.filter(is_active=True).first()
        if active_theme:
            return Response(ThemeSerializer(active_theme).data)
        # Если нет активной, вернуть тему по умолчанию
        default_theme = Theme.objects.filter(is_default=True).first()
        if default_theme:
            return Response(ThemeSerializer(default_theme).data)
        return Response({'detail': 'Активная тема не найдена'}, status=status.HTTP_404_NOT_FOUND)
    
    @action(detail=True, methods=['post'], url_path='activate')
    def activate_theme(self, request, pk=None):
        """Активировать тему"""
        theme = self.get_object()
        # Снимаем активацию со всех остальных тем
        Theme.objects.filter(is_active=True).update(is_active=False)
        theme.is_active = True
        theme.save()
        return Response(ThemeSerializer(theme).data)
    
    @action(detail=True, methods=['post'], url_path='duplicate')
    def duplicate_theme(self, request, pk=None):
        """Создать копию темы"""
        source_theme = self.get_object()
        new_name = request.data.get('name', f'{source_theme.name} (копия)')
        
        new_theme = Theme.objects.create(
            name=new_name,
            description=source_theme.description,
            author=request.data.get('author', source_theme.author),
            base_theme=source_theme.base_theme,
            colors=source_theme.colors.copy(),
            bootstrap_colors=source_theme.bootstrap_colors.copy() if source_theme.bootstrap_colors else {},
            is_active=False,
            is_default=False,
            is_system=False
        )
        return Response(ThemeSerializer(new_theme).data, status=status.HTTP_201_CREATED)
    
    @action(detail=True, methods=['get'], url_path='export')
    def export_theme(self, request, pk=None):
        """Экспорт темы в JSON файл"""
        theme = self.get_object()
        
        export_data = {
            'name': theme.name,
            'description': theme.description,
            'author': theme.author,
            'base_theme': theme.base_theme,
            'colors': theme.colors,
            'bootstrap_colors': theme.bootstrap_colors,
            'version': '1.0',
            'exported_at': str(timezone.now())
        }
        
        response = HttpResponse(
            json.dumps(export_data, indent=2, ensure_ascii=False),
            content_type='application/json; charset=utf-8'
        )
        safe_name = _safe_content_disposition_filename(theme.name.replace(' ', '-').lower()) + '.json'
        response['Content-Disposition'] = f'attachment; filename="{safe_name}"'
        return response
    
    @action(detail=False, methods=['post'], url_path='import')
    def import_theme(self, request):
        """Импорт темы из JSON файла"""
        try:
            file_content = self._read_theme_json(request)
            if file_content is None:
                return Response(
                    {'error': 'Файл не передан'},
                    status=status.HTTP_400_BAD_REQUEST,
                )
            theme_data = json.loads(file_content)
            
            # Валидация обязательных полей
            required_fields = ['name', 'base_theme', 'colors']
            for field in required_fields:
                if field not in theme_data:
                    return Response(
                        {'error': f'Отсутствует обязательное поле: {field}'},
                        status=status.HTTP_400_BAD_REQUEST
                    )
            
            # Создаем новую тему
            new_theme = Theme.objects.create(
                name=theme_data['name'],
                description=theme_data.get('description', ''),
                author=theme_data.get('author', ''),
                base_theme=theme_data['base_theme'],
                colors=theme_data['colors'],
                bootstrap_colors=theme_data.get('bootstrap_colors', {}),
                is_active=False,
                is_default=False,
                is_system=False
            )
            
            return Response(
                ThemeSerializer(new_theme).data,
                status=status.HTTP_201_CREATED
            )
        except json.JSONDecodeError:
            return Response(
                {'error': 'Неверный формат JSON'},
                status=status.HTTP_400_BAD_REQUEST
            )
        except Exception:
            logger.exception('Ошибка импорта темы')
            return Response(
                {'error': 'Не удалось импортировать тему.'},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )
    
    @action(detail=True, methods=['post'], url_path='reset-defaults')
    def reset_defaults(self, request, pk=None):
        """Сбросить системную тему к начальным значениям"""
        from src.core.settings.services.theme_seed import reset_system_theme_to_defaults

        theme = self.get_object()
        if not theme.is_system:
            return Response(
                {'error': 'Сброс доступен только для системных тем'},
                status=status.HTTP_400_BAD_REQUEST,
            )
        if not reset_system_theme_to_defaults(theme):
            return Response(
                {'error': 'Не удалось определить начальные значения темы'},
                status=status.HTTP_400_BAD_REQUEST,
            )
        theme.refresh_from_db()
        return Response(ThemeSerializer(theme).data)

    @action(detail=False, methods=['post'], url_path='create-system-themes')
    def create_system_themes(self, request):
        """Создать или обновить системные темы (light и dark)"""
        from src.core.settings.services.theme_seed import ensure_system_themes

        created, updated = ensure_system_themes(Theme, update_existing=True)

        message = []
        if created:
            message.append(f'Создано {len(created)} тем')
        if updated:
            message.append(f'Обновлено {len(updated)} тем')

        return Response({
            'message': ', '.join(message) if message else 'Темы актуальны',
            'created': [ThemeSerializer(theme).data for theme in created],
            'updated': [ThemeSerializer(theme).data for theme in updated],
        })