"""
Сериализаторы для управления меню.
"""

from rest_framework import serializers
from rest_framework.serializers import (
    ModelSerializer,
    CharField,
    ValidationError,
    Serializer,
    ListField,
)

from src.core.cms.adp.models import Role, RoleGroup, UserRole
from src.core.cms.adp.serializers import RoleSerializer, RoleGroupSerializer
from .models import MenuItem, MenuSeparator, MenuAccessLog


class MenuItemChildSerializer(ModelSerializer):
    """Сериализатор для дочерних элементов меню (без рекурсии)"""
    
    class Meta:
        model = MenuItem
        fields = [
            'id', 'name', 'route_name', 'icon', 'item_type',
            'page', 'order', 'is_active'
        ]


class MenuItemSerializer(ModelSerializer):
    """Сериализатор для элементов меню"""
    children = MenuItemChildSerializer(many=True, read_only=True)
    parent_name = CharField(source='parent.name', read_only=True, allow_null=True)
    allowed_roles_data = RoleSerializer(source='allowed_roles', many=True, read_only=True)
    allowed_role_groups_data = RoleGroupSerializer(source='allowed_role_groups', many=True, read_only=True)
    
    class Meta:
        model = MenuItem
        fields = [
            'id', 'name', 'route_name', 'icon', 'item_type',
            'page', 'external_url', 'parent', 'parent_name',
            'order', 'is_active', 'is_admin_only',
            'allowed_roles', 'allowed_roles_data',
            'allowed_role_groups', 'allowed_role_groups_data',
            'module_source', 'children', 'created_at', 'updated_at'
        ]
        read_only_fields = ['id', 'created_at', 'updated_at', 'children']


class MenuItemTreeSerializer(ModelSerializer):
    """Рекурсивный сериализатор для дерева меню"""
    children = serializers.SerializerMethodField()
    
    class Meta:
        model = MenuItem
        fields = [
            'id', 'name', 'route_name', 'icon', 'item_type',
            'page', 'external_url', 'order', 'children'
        ]
    
    def get_children(self, obj):
        # Получаем контекст с информацией о пользователе
        user = self.context.get('user')
        children = obj.children.filter(is_active=True).order_by('order')
        
        if user:
            # Фильтруем по правам доступа
            children = self._filter_by_access(children, user)
        
        return MenuItemTreeSerializer(children, many=True, context=self.context).data
    
    def _filter_by_access(self, items, user):
        """Фильтрует элементы меню по правам доступа пользователя"""
        if user.is_superuser:
            return items
        
        filtered_ids = []
        for item in items:
            # Проверяем admin_only
            if item.is_admin_only:
                # Проверяем, является ли пользователь администратором
                user_role = UserRole.objects.filter(user=user, is_active=True).first()
                if not user_role or user_role.role.role_type != 'admin':
                    continue
            
            # Проверяем allowed_roles
            if item.allowed_roles.exists():
                user_role = UserRole.objects.filter(user=user, is_active=True).first()
                if not user_role or not item.allowed_roles.filter(id=user_role.role.id).exists():
                    continue
            
            # Проверяем allowed_role_groups
            if item.allowed_role_groups.exists():
                user_role = UserRole.objects.filter(user=user, is_active=True).first()
                if not user_role:
                    continue
                user_groups = user_role.role_groups.all()
                if not item.allowed_role_groups.filter(id__in=user_groups).exists():
                    continue
            
            filtered_ids.append(item.id)
        
        return items.filter(id__in=filtered_ids)


class MenuSeparatorSerializer(ModelSerializer):
    """Сериализатор для разделителей меню"""
    
    class Meta:
        model = MenuSeparator
        fields = [
            'id', 'name', 'before_order', 'is_active',
            'created_at', 'updated_at'
        ]
        read_only_fields = ['id', 'created_at', 'updated_at']


class UserMenuSerializer(Serializer):
    """Сериализатор для получения меню пользователя"""
    menu_items = MenuItemTreeSerializer(many=True, read_only=True)
    separators = MenuSeparatorSerializer(many=True, read_only=True)


class MenuItemCreateSerializer(ModelSerializer):
    """Сериализатор для создания элемента меню"""
    
    class Meta:
        model = MenuItem
        fields = [
            'name', 'route_name', 'icon', 'item_type',
            'page', 'external_url', 'parent', 'order',
            'is_active', 'is_admin_only', 'allowed_roles',
            'allowed_role_groups', 'module_source'
        ]
    
    def validate(self, attrs):
        item_type = attrs.get('item_type', 'route')
        
        # Валидация для offcanvas
        if item_type == 'offcanvas' and not attrs.get('page'):
            raise ValidationError({'page': 'Страница обязательна для типа "offcanvas"'})
        
        # Валидация для внешних ссылок
        if item_type == 'external' and not attrs.get('external_url'):
            raise ValidationError({'external_url': 'URL обязателен для типа "external"'})
        
        return attrs


class MenuItemUpdateSerializer(ModelSerializer):
    """Сериализатор для обновления элемента меню"""
    
    class Meta:
        model = MenuItem
        fields = [
            'name', 'route_name', 'icon', 'item_type',
            'page', 'external_url', 'parent', 'order',
            'is_active', 'is_admin_only', 'allowed_roles',
            'allowed_role_groups', 'module_source'
        ]


class MenuItemReorderSerializer(Serializer):
    """Сериализатор для изменения порядка элементов меню"""
    items = ListField(
        child=serializers.DictField(),
        help_text='Список объектов с id, order и опционально parent_id'
    )
    
    def validate_items(self, value):
        for item in value:
            if 'id' not in item or 'order' not in item:
                raise ValidationError('Каждый элемент должен содержать id и order')
            # parent_id опционален, но если есть - должен быть числом или None
            if 'parent_id' in item and item['parent_id'] is not None:
                try:
                    int(item['parent_id'])
                except (ValueError, TypeError):
                    raise ValidationError(f'parent_id должен быть числом или null для элемента {item.get("id")}')
        return value


class MenuAccessLogSerializer(ModelSerializer):
    """Сериализатор для логов доступа к меню"""
    username = CharField(source='user.username', read_only=True)
    menu_item_name = CharField(source='menu_item.name', read_only=True)
    
    class Meta:
        model = MenuAccessLog
        fields = [
            'id', 'user', 'username', 'menu_item', 
            'menu_item_name', 'accessed_at'
        ]
        read_only_fields = ['id', 'accessed_at']

