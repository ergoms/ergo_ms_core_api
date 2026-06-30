"""
API Views для управления меню.
Предоставляет CRUD операции для элементов меню и разделителей.
"""

from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from drf_yasg.utils import swagger_auto_schema
from drf_yasg import openapi

from src.core.cms.adp.services.permissions import PermissionService
from .access import user_can_see_menu_item
from .models import MenuItem, MenuSeparator, MenuAccessLog
from .serializers import (
    MenuItemSerializer, MenuItemTreeSerializer, MenuSeparatorSerializer,
    MenuItemCreateSerializer, MenuItemUpdateSerializer, 
    MenuItemReorderSerializer, MenuAccessLogSerializer
)


class BaseMenuAPIView(APIView):
    """Базовый класс для API меню"""
    permission_classes = [IsAuthenticated]
    
    def is_admin(self, user):
        return PermissionService.can_manage_users_as_global_admin(user)


class UserMenuView(BaseMenuAPIView):
    """
    Получение меню для текущего пользователя.
    Возвращает отфильтрованное меню с учетом прав доступа.
    """
    
    @swagger_auto_schema(
        operation_description="Получить меню для текущего пользователя",
        responses={
            200: openapi.Response(
                description="Меню пользователя",
                schema=openapi.Schema(
                    type=openapi.TYPE_OBJECT,
                    properties={
                        'menu_items': openapi.Schema(
                            type=openapi.TYPE_ARRAY,
                            items=openapi.Schema(type=openapi.TYPE_OBJECT)
                        ),
                        'separators': openapi.Schema(
                            type=openapi.TYPE_ARRAY,
                            items=openapi.Schema(type=openapi.TYPE_OBJECT)
                        )
                    }
                )
            ),
            401: "Не авторизован"
        },
        tags=['Menu']
    )
    def get(self, request):
        user = request.user
        
        # Получаем корневые элементы меню (без родителя)
        root_items = MenuItem.objects.filter(
            parent__isnull=True, 
            is_active=True
        ).order_by('order')
        
        filtered_items = self._filter_menu_items(root_items, user)

        items_data = MenuItemTreeSerializer(
            filtered_items,
            many=True,
            context={'user': user},
        ).data
        
        # Получаем активные разделители
        separators = MenuSeparator.objects.filter(is_active=True).order_by('before_order')
        separators_data = MenuSeparatorSerializer(separators, many=True).data
        
        return Response({
            'menu_items': items_data,
            'separators': separators_data
        })
    
    def _filter_menu_items(self, items, user):
        """Фильтрует элементы меню по правам доступа"""
        filtered_ids = []
        for item in items:
            if user_can_see_menu_item(item, user):
                filtered_ids.append(item.id)

        return items.filter(id__in=filtered_ids)


class MenuItemListView(BaseMenuAPIView):
    """
    Список всех элементов меню (для администраторов).
    """
    
    @swagger_auto_schema(
        operation_description="Получить список всех элементов меню",
        manual_parameters=[
            openapi.Parameter(
                'parent_id',
                openapi.IN_QUERY,
                description="ID родительского элемента (null для корневых)",
                type=openapi.TYPE_INTEGER,
                required=False
            ),
            openapi.Parameter(
                'include_inactive',
                openapi.IN_QUERY,
                description="Включать неактивные элементы",
                type=openapi.TYPE_BOOLEAN,
                required=False
            )
        ],
        responses={
            200: MenuItemSerializer(many=True),
            401: "Не авторизован",
            403: "Нет доступа"
        },
        tags=['Menu Admin']
    )
    def get(self, request):
        if not self.is_admin(request.user):
            return Response(
                {'error': 'Доступ запрещён'},
                status=status.HTTP_403_FORBIDDEN
            )
        
        parent_id = request.query_params.get('parent_id')
        include_inactive = request.query_params.get('include_inactive', 'false').lower() == 'true'
        
        queryset = MenuItem.objects.all()
        
        if parent_id:
            if parent_id == 'null':
                queryset = queryset.filter(parent__isnull=True)
            else:
                queryset = queryset.filter(parent_id=parent_id)
        
        if not include_inactive:
            queryset = queryset.filter(is_active=True)
        
        # Сортируем сначала по parent_id (null первыми), потом по order
        # Это гарантирует правильный порядок элементов одного уровня
        queryset = queryset.order_by('parent_id', 'order')
        serializer = MenuItemSerializer(queryset, many=True)
        
        return Response(serializer.data)
    
    @swagger_auto_schema(
        operation_description="Создать новый элемент меню",
        request_body=MenuItemCreateSerializer,
        responses={
            201: MenuItemSerializer,
            400: "Ошибка валидации",
            401: "Не авторизован",
            403: "Нет доступа"
        },
        tags=['Menu Admin']
    )
    def post(self, request):
        if not self.is_admin(request.user):
            return Response(
                {'error': 'Доступ запрещён'},
                status=status.HTTP_403_FORBIDDEN
            )
        
        serializer = MenuItemCreateSerializer(data=request.data)
        if serializer.is_valid():
            item = serializer.save()
            return Response(
                MenuItemSerializer(item).data,
                status=status.HTTP_201_CREATED
            )
        
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


class MenuItemDetailView(BaseMenuAPIView):
    """
    Детальное представление элемента меню.
    """
    
    @swagger_auto_schema(
        operation_description="Получить элемент меню по ID",
        responses={
            200: MenuItemSerializer,
            401: "Не авторизован",
            403: "Нет доступа",
            404: "Не найдено"
        },
        tags=['Menu Admin']
    )
    def get(self, request, item_id):
        if not self.is_admin(request.user):
            return Response(
                {'error': 'Доступ запрещён'},
                status=status.HTTP_403_FORBIDDEN
            )
        
        try:
            item = MenuItem.objects.get(id=item_id)
        except MenuItem.DoesNotExist:
            return Response(
                {'error': 'Элемент меню не найден'},
                status=status.HTTP_404_NOT_FOUND
            )
        
        serializer = MenuItemSerializer(item)
        return Response(serializer.data)
    
    @swagger_auto_schema(
        operation_description="Обновить элемент меню",
        request_body=MenuItemUpdateSerializer,
        responses={
            200: MenuItemSerializer,
            400: "Ошибка валидации",
            401: "Не авторизован",
            403: "Нет доступа",
            404: "Не найдено"
        },
        tags=['Menu Admin']
    )
    def put(self, request, item_id):
        if not self.is_admin(request.user):
            return Response(
                {'error': 'Доступ запрещён'},
                status=status.HTTP_403_FORBIDDEN
            )
        
        try:
            item = MenuItem.objects.get(id=item_id)
        except MenuItem.DoesNotExist:
            return Response(
                {'error': 'Элемент меню не найден'},
                status=status.HTTP_404_NOT_FOUND
            )
        
        serializer = MenuItemUpdateSerializer(item, data=request.data, partial=True)
        if serializer.is_valid():
            item = serializer.save()
            return Response(MenuItemSerializer(item).data)
        
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
    
    @swagger_auto_schema(
        operation_description="Удалить элемент меню",
        responses={
            204: "Успешно удалено",
            401: "Не авторизован",
            403: "Нет доступа",
            404: "Не найдено"
        },
        tags=['Menu Admin']
    )
    def delete(self, request, item_id):
        if not self.is_admin(request.user):
            return Response(
                {'error': 'Доступ запрещён'},
                status=status.HTTP_403_FORBIDDEN
            )
        
        try:
            item = MenuItem.objects.get(id=item_id)
        except MenuItem.DoesNotExist:
            return Response(
                {'error': 'Элемент меню не найден'},
                status=status.HTTP_404_NOT_FOUND
            )
        
        item.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)


class MenuItemReorderView(BaseMenuAPIView):
    """
    Изменение порядка элементов меню.
    """
    
    @swagger_auto_schema(
        operation_description="Изменить порядок элементов меню",
        request_body=MenuItemReorderSerializer,
        responses={
            200: "Порядок обновлён",
            400: "Ошибка валидации",
            401: "Не авторизован",
            403: "Нет доступа"
        },
        tags=['Menu Admin']
    )
    def post(self, request):
        if not self.is_admin(request.user):
            return Response(
                {'error': 'Доступ запрещён'},
                status=status.HTTP_403_FORBIDDEN
            )
        
        serializer = MenuItemReorderSerializer(data=request.data)
        if serializer.is_valid():
            items_data = serializer.validated_data['items']
            
            for item_data in items_data:
                try:
                    item = MenuItem.objects.get(id=item_data['id'])
                    item.order = item_data['order']
                    
                    # Обновляем parent_id если он передан
                    if 'parent_id' in item_data:
                        parent_id = item_data['parent_id']
                        if parent_id is None:
                            item.parent = None
                        else:
                            try:
                                parent = MenuItem.objects.get(id=parent_id)
                                item.parent = parent
                            except MenuItem.DoesNotExist:
                                pass
                    
                    # Определяем какие поля обновлять
                    update_fields = ['order']
                    if 'parent_id' in item_data:
                        update_fields.append('parent')
                    
                    item.save(update_fields=update_fields)
                except MenuItem.DoesNotExist:
                    continue
            
            return Response({'message': 'Порядок обновлён'})
        
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


class MenuSeparatorListView(BaseMenuAPIView):
    """
    Список разделителей меню.
    """
    
    @swagger_auto_schema(
        operation_description="Получить список разделителей меню",
        responses={
            200: MenuSeparatorSerializer(many=True),
            401: "Не авторизован",
            403: "Нет доступа"
        },
        tags=['Menu Admin']
    )
    def get(self, request):
        if not self.is_admin(request.user):
            return Response(
                {'error': 'Доступ запрещён'},
                status=status.HTTP_403_FORBIDDEN
            )
        
        separators = MenuSeparator.objects.all().order_by('before_order')
        serializer = MenuSeparatorSerializer(separators, many=True)
        return Response(serializer.data)
    
    @swagger_auto_schema(
        operation_description="Создать разделитель меню",
        request_body=MenuSeparatorSerializer,
        responses={
            201: MenuSeparatorSerializer,
            400: "Ошибка валидации",
            401: "Не авторизован",
            403: "Нет доступа"
        },
        tags=['Menu Admin']
    )
    def post(self, request):
        if not self.is_admin(request.user):
            return Response(
                {'error': 'Доступ запрещён'},
                status=status.HTTP_403_FORBIDDEN
            )
        
        serializer = MenuSeparatorSerializer(data=request.data)
        if serializer.is_valid():
            separator = serializer.save()
            return Response(
                MenuSeparatorSerializer(separator).data,
                status=status.HTTP_201_CREATED
            )
        
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


class MenuSeparatorDetailView(BaseMenuAPIView):
    """
    Детальное представление разделителя меню.
    """
    
    @swagger_auto_schema(
        operation_description="Получить разделитель по ID",
        responses={
            200: MenuSeparatorSerializer,
            401: "Не авторизован",
            403: "Нет доступа",
            404: "Не найдено"
        },
        tags=['Menu Admin']
    )
    def get(self, request, separator_id):
        if not self.is_admin(request.user):
            return Response(
                {'error': 'Доступ запрещён'},
                status=status.HTTP_403_FORBIDDEN
            )
        
        try:
            separator = MenuSeparator.objects.get(id=separator_id)
        except MenuSeparator.DoesNotExist:
            return Response(
                {'error': 'Разделитель не найден'},
                status=status.HTTP_404_NOT_FOUND
            )
        
        serializer = MenuSeparatorSerializer(separator)
        return Response(serializer.data)
    
    @swagger_auto_schema(
        operation_description="Обновить разделитель меню",
        request_body=MenuSeparatorSerializer,
        responses={
            200: MenuSeparatorSerializer,
            400: "Ошибка валидации",
            401: "Не авторизован",
            403: "Нет доступа",
            404: "Не найдено"
        },
        tags=['Menu Admin']
    )
    def put(self, request, separator_id):
        if not self.is_admin(request.user):
            return Response(
                {'error': 'Доступ запрещён'},
                status=status.HTTP_403_FORBIDDEN
            )
        
        try:
            separator = MenuSeparator.objects.get(id=separator_id)
        except MenuSeparator.DoesNotExist:
            return Response(
                {'error': 'Разделитель не найден'},
                status=status.HTTP_404_NOT_FOUND
            )
        
        serializer = MenuSeparatorSerializer(separator, data=request.data, partial=True)
        if serializer.is_valid():
            separator = serializer.save()
            return Response(MenuSeparatorSerializer(separator).data)
        
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
    
    @swagger_auto_schema(
        operation_description="Удалить разделитель меню",
        responses={
            204: "Успешно удалено",
            401: "Не авторизован",
            403: "Нет доступа",
            404: "Не найдено"
        },
        tags=['Menu Admin']
    )
    def delete(self, request, separator_id):
        if not self.is_admin(request.user):
            return Response(
                {'error': 'Доступ запрещён'},
                status=status.HTTP_403_FORBIDDEN
            )
        
        try:
            separator = MenuSeparator.objects.get(id=separator_id)
        except MenuSeparator.DoesNotExist:
            return Response(
                {'error': 'Разделитель не найден'},
                status=status.HTTP_404_NOT_FOUND
            )
        
        separator.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)


class MenuAccessLogView(BaseMenuAPIView):
    """
    Логирование доступа к элементам меню.
    """
    
    @swagger_auto_schema(
        operation_description="Записать лог доступа к элементу меню",
        request_body=openapi.Schema(
            type=openapi.TYPE_OBJECT,
            properties={
                'menu_item_id': openapi.Schema(type=openapi.TYPE_INTEGER)
            },
            required=['menu_item_id']
        ),
        responses={
            201: "Лог записан",
            400: "Ошибка валидации",
            401: "Не авторизован",
            404: "Элемент меню не найден"
        },
        tags=['Menu']
    )
    def post(self, request):
        menu_item_id = request.data.get('menu_item_id')
        
        if not menu_item_id:
            return Response(
                {'error': 'menu_item_id обязателен'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        try:
            menu_item = MenuItem.objects.get(id=menu_item_id)
        except MenuItem.DoesNotExist:
            return Response(
                {'error': 'Элемент меню не найден'},
                status=status.HTTP_404_NOT_FOUND
            )
        
        MenuAccessLog.objects.create(
            user=request.user,
            menu_item=menu_item
        )
        
        return Response({'message': 'Лог записан'}, status=status.HTTP_201_CREATED)


class AvailableIconsView(BaseMenuAPIView):
    """
    Получение списка доступных иконок Lucide.
    """
    
    @swagger_auto_schema(
        operation_description="Получить список доступных иконок",
        responses={
            200: openapi.Response(
                description="Список иконок",
                schema=openapi.Schema(
                    type=openapi.TYPE_ARRAY,
                    items=openapi.Schema(type=openapi.TYPE_STRING)
                )
            ),
            401: "Не авторизован",
            403: "Нет доступа"
        },
        tags=['Menu Admin']
    )
    def get(self, request):
        if not self.is_admin(request.user):
            return Response(
                {'error': 'Доступ запрещён'},
                status=status.HTTP_403_FORBIDDEN
            )
        
        # Возвращаем часто используемые иконки Lucide
        icons = [
            'CircleUserRound', 'UserCog', 'Settings', 'Cog', 'Home',
            'LayoutDashboard', 'BarChart', 'PieChart', 'LineChart',
            'Database', 'Server', 'Cloud', 'Folder', 'File', 'FileText',
            'Image', 'Video', 'Music', 'Camera', 'Mail', 'MessageSquare',
            'Bell', 'Calendar', 'Clock', 'Search', 'Filter', 'Star',
            'Heart', 'Bookmark', 'Tag', 'Link', 'ExternalLink', 'Download',
            'Upload', 'Share', 'Copy', 'Clipboard', 'Check', 'X', 'Plus',
            'Minus', 'Edit', 'Trash', 'Archive', 'RefreshCw', 'RotateCcw',
            'ChevronRight', 'ChevronLeft', 'ChevronUp', 'ChevronDown',
            'ArrowRight', 'ArrowLeft', 'ArrowUp', 'ArrowDown', 'Move',
            'Users', 'User', 'UserPlus', 'UserMinus', 'UserCheck', 'UserX',
            'Lock', 'Unlock', 'Key', 'KeySquare', 'Shield', 'ShieldCheck',
            'Eye', 'EyeOff', 'Layers', 'Grid', 'List', 'Menu', 'MoreHorizontal',
            'MoreVertical', 'Info', 'HelpCircle', 'AlertCircle', 'AlertTriangle',
            'Zap', 'Activity', 'TrendingUp', 'TrendingDown', 'DollarSign',
            'CreditCard', 'ShoppingCart', 'Package', 'Truck', 'Map', 'MapPin',
            'Globe', 'Compass', 'Target', 'Award', 'Trophy', 'Gift', 'Percent'
        ]
        
        return Response(icons)


class MenuRestoreView(BaseMenuAPIView):
    """Восстановление пунктов меню из populate-функций миграций."""

    @swagger_auto_schema(
        operation_description="Восстановить меню из миграций ядра и модулей (restore_menu)",
        responses={
            200: "Меню восстановлено",
            401: "Не авторизован",
            403: "Нет доступа",
            400: "Ошибка восстановления",
        },
        tags=['Menu Admin'],
    )
    def post(self, request):
        if not self.is_admin(request.user):
            return Response(
                {'error': 'Доступ запрещён'},
                status=status.HTTP_403_FORBIDDEN,
            )

        from django.core.management import call_command
        from io import StringIO

        buffer = StringIO()
        try:
            call_command('restore_menu', stdout=buffer)
            return Response({
                'message': 'Меню восстановлено из миграций',
                'details': buffer.getvalue(),
            })
        except Exception as exc:
            return Response(
                {'error': str(exc)},
                status=status.HTTP_400_BAD_REQUEST,
            )