import os
import re
import json
from django.utils import timezone
from rest_framework.response import Response
from rest_framework import viewsets, status
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated, AllowAny
from django.http import HttpResponse

from .permissions import IsGlobalAdmin

from .models import Category
from .serializers import CategorySerializer
from .models import UserAvatar
from .serializers import UserAvatarSerializer
from rest_framework.permissions import IsAuthenticated
from src.core.utils.mixins import MediaApiFileMixin
from django.forms.models import model_to_dict
from .audit import log_audit
from .models import AuditLog
from .serializers import AuditLogSerializer
from rest_framework.viewsets import ReadOnlyModelViewSet

from .models import *
from .serializers import *

from .models import AuditLog
from .serializers import AuditLogSerializer


def _safe_content_disposition_filename(name):
    """Санитизирует имя файла для заголовка Content-Disposition (защита от response splitting)."""
    if name is None:
        return 'download'
    s = re.sub(r'[\x00-\x1f\x7f"\\\r\n]', '', str(name).strip())
    s = s[:200] if len(s) > 200 else s
    return s or 'download'


class GeneralSettingsViewSet(viewsets.ModelViewSet):
    queryset = GeneralSettings.objects.all()
    serializer_class = GeneralSettingsSerializer

    def get_permissions(self):
        if self.action == 'get_site_name':
            return [AllowAny()]
        return [IsAuthenticated(), IsGlobalAdmin()]

    @action(detail=False, methods=['get'], url_path='last')
    def get_last_settings(self, request):
        last_settings = self.queryset.order_by('-id').first()
        if last_settings:
            from .serializers import GeneralSettingsReadSerializer
            serializer = GeneralSettingsReadSerializer(last_settings)
            return Response(serializer.data)
        return Response({'detail': 'Нет ни одной записи настроек.'}, status=status.HTTP_404_NOT_FOUND)
    
    @action(detail=False, methods=['get'], url_path='site-name')
    def get_site_name(self, request):
        """Легковесный endpoint для получения только названия сайта (для меню)"""
        last_settings = self.queryset.order_by('-id').first()
        if last_settings:
            from .serializers import GeneralSettingsSiteNameSerializer
            serializer = GeneralSettingsSiteNameSerializer(last_settings)
            return Response(serializer.data)
        return Response({'site_name': 'ERGOMS'}, status=status.HTTP_200_OK)
    
    def perform_update(self, serializer):
        old_obj = self.get_object()
        old_data = model_to_dict(old_obj)

        new_obj = serializer.save()
        new_data = model_to_dict(new_obj)

        diff = {
            field: [old_data[field], new_data[field]]
            for field in old_data
            if old_data[field] != new_data[field]
        }

        if diff:
            log_audit(self.request, new_obj, 'UPDATE', diff)

    def perform_destroy(self, instance):
        log_audit(self.request, instance, 'DELETE')

        instance.delete()

class AppearanceSettingsViewSet(viewsets.ModelViewSet):
    queryset = AppearanceSettings.objects.all()
    serializer_class = AppearanceSettingsSerializer
    
    @action(detail=False, methods=['get'], url_path='last')
    def get_last_settings(self, request):
        """Получить последние настройки внешнего вида"""
        last_settings = self.queryset.order_by('-id').first()
        if last_settings:
            serializer = self.get_serializer(last_settings)
            return Response(serializer.data)
        return Response({'detail': 'Нет ни одной записи настроек.'}, status=status.HTTP_404_NOT_FOUND)
    
    @action(detail=False, methods=['post'], url_path='export-theme')
    def export_theme(self, request):
        """Экспорт темы в JSON файл"""
        theme_config = request.data.get('theme_config', {})
        theme_name = request.data.get('theme_name', 'custom-theme')
        
        if not theme_config:
            return Response(
                {'error': 'theme_config обязателен'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        # Формируем JSON для экспорта
        export_data = {
            'name': theme_name,
            'version': '1.0.0',
            'description': request.data.get('description', ''),
            'author': request.data.get('author', ''),
            'config': theme_config,
            'exported_at': str(timezone.now())
        }
        
        response = HttpResponse(
            json.dumps(export_data, indent=2, ensure_ascii=False),
            content_type='application/json; charset=utf-8'
        )
        safe_filename = _safe_content_disposition_filename(theme_name) + '.json'
        response['Content-Disposition'] = f'attachment; filename="{safe_filename}"'
        return response
    
    @action(detail=False, methods=['post'], url_path='import-theme')
    def import_theme(self, request):
        """Импорт темы из JSON файла"""
        file = request.FILES.get('file')
        if not file:
            return Response(
                {'error': 'Файл не передан'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        try:
            # Читаем JSON из файла
            file_content = file.read().decode('utf-8')
            theme_data = json.loads(file_content)
            
            # Валидация структуры
            if 'config' not in theme_data:
                return Response(
                    {'error': 'Неверный формат файла темы'},
                    status=status.HTTP_400_BAD_REQUEST
                )
            
            # Возвращаем конфигурацию темы
            return Response({
                'name': theme_data.get('name', 'imported-theme'),
                'description': theme_data.get('description', ''),
                'author': theme_data.get('author', ''),
                'config': theme_data['config']
            })
        except json.JSONDecodeError:
            return Response(
                {'error': 'Неверный формат JSON'},
                status=status.HTTP_400_BAD_REQUEST
            )
        except Exception as e:
            return Response(
                {'error': f'Ошибка при импорте: {str(e)}'},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )

class SecuritySettingsViewSet(viewsets.ModelViewSet):
    queryset = SecuritySettings.objects.all()
    serializer_class = SecuritySettingsSerializer

class MediaSettingsViewSet(viewsets.ModelViewSet):
    queryset = MediaSettings.objects.all()
    serializer_class = MediaSettingsSerializer

class PermalinkSettingsViewSet(viewsets.ModelViewSet):
    queryset = PermalinkSettings.objects.all()
    serializer_class = PermalinkSettingsSerializer

class EmailSettingsViewSet(viewsets.ModelViewSet):
    queryset = EmailSettings.objects.all()
    serializer_class = EmailSettingsSerializer
class CategoryViewSet(viewsets.ModelViewSet):
    queryset = Category.objects.all()
    serializer_class = CategorySerializer
class TagViewSet(viewsets.ModelViewSet):
    queryset = Tag.objects.all()
    serializer_class = TagSerializer

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
            file, file_path = self.get_file_or_path('image')
            instance = serializer.save(user=self.request.user)
            if file_path:
                self.assign_file_field(instance, 'image', file_path=file_path)
                instance.save()
    
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

class AuditLogViewSet(ReadOnlyModelViewSet):
    queryset = AuditLog.objects.all()
    serializer_class = AuditLogSerializer
    permission_classes = [IsAuthenticated, IsGlobalAdmin]
    filterset_fields = ['content_type__model', 'object_id', 'action']
    ordering = ['-timestamp']


class ThemeViewSet(viewsets.ModelViewSet):
    """ViewSet для управления темами оформления"""
    queryset = Theme.objects.all()
    serializer_class = ThemeSerializer
    permission_classes = [IsAuthenticated]
    
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
        file = request.FILES.get('file')
        if not file:
            return Response(
                {'error': 'Файл не передан'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        try:
            file_content = file.read().decode('utf-8')
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
        except Exception as e:
            return Response(
                {'error': f'Ошибка при импорте: {str(e)}'},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )
    
    @action(detail=False, methods=['post'], url_path='create-system-themes')
    def create_system_themes(self, request):
        """Создать или обновить системные темы (light и dark)"""
        created = []
        updated = []
        
        # Светлая тема
        light_theme, light_created = Theme.objects.get_or_create(
            name='Светлая', is_system=True,
            defaults={
                'description': 'Системная светлая тема',
                'author': 'System',
                'base_theme': 'light',
                'colors': Theme.get_default_colors('light'),
                'bootstrap_colors': {},  # Пустой - используем SCSS
                'is_active': False,
                'is_default': True,
            }
        )
        if light_created:
            created.append(ThemeSerializer(light_theme).data)
        else:
            # Обновляем существующую - сбрасываем bootstrap_colors
            light_theme.colors = Theme.get_default_colors('light')
            light_theme.bootstrap_colors = {}
            light_theme.save()
            updated.append(ThemeSerializer(light_theme).data)
        
        # Тёмная тема
        dark_theme, dark_created = Theme.objects.get_or_create(
            name='Тёмная', is_system=True,
            defaults={
                'description': 'Системная тёмная тема',
                'author': 'System',
                'base_theme': 'dark',
                'colors': Theme.get_default_colors('dark'),
                'bootstrap_colors': {},  # Пустой - используем SCSS
                'is_active': False,
                'is_default': False,
            }
        )
        if dark_created:
            created.append(ThemeSerializer(dark_theme).data)
        else:
            # Обновляем существующую - сбрасываем bootstrap_colors
            dark_theme.colors = Theme.get_default_colors('dark')
            dark_theme.bootstrap_colors = {}
            dark_theme.save()
            updated.append(ThemeSerializer(dark_theme).data)
        
        message = []
        if created:
            message.append(f'Создано {len(created)} тем')
        if updated:
            message.append(f'Обновлено {len(updated)} тем')
        
        return Response({
            'message': ', '.join(message) if message else 'Темы актуальны',
            'created': created,
            'updated': updated
        }, status=status.HTTP_200_OK)