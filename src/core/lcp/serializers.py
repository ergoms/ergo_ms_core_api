from rest_framework import serializers

from .models import (
    LcpModule, LcpPage, LcpComponentCategory, LcpComponentTemplate,
    LcpDataSource, LcpDatabaseTable, LcpAction, LcpVariable, LcpAuditLog
)


class LcpModuleSerializer(serializers.ModelSerializer):
    pages_count = serializers.SerializerMethodField()
    
    class Meta:
        model = LcpModule
        fields = [
            'id', 'name', 'slug', 'description', 'icon', 'color',
            'settings', 'global_variables', 'menu_order', 'is_active',
            'pages_count', 'created_at', 'updated_at'
        ]
        read_only_fields = ['created_at', 'updated_at']
    
    def get_pages_count(self, obj):
        return obj.pages.count()


class LcpModuleListSerializer(serializers.ModelSerializer):
    """Сокращённый сериализатор для списка"""
    pages_count = serializers.SerializerMethodField()
    
    class Meta:
        model = LcpModule
        fields = ['id', 'name', 'slug', 'icon', 'color', 'menu_order', 'is_active', 'pages_count']
    
    def get_pages_count(self, obj):
        return obj.pages.count()


class LcpPageSerializer(serializers.ModelSerializer):
    module_name = serializers.CharField(source='module.name', read_only=True)
    full_url = serializers.ReadOnlyField()
    
    class Meta:
        model = LcpPage
        fields = [
            'id', 'name', 'slug', 'module', 'module_name',
            'component_tree', 'settings', 'variables', 'data_sources',
            'breakpoints', 'is_draft', 'is_template', 'is_homepage',
            'menu_order', 'show_in_menu', 'icon', 'full_url',
            'created_at', 'updated_at'
        ]
        read_only_fields = ['created_at', 'updated_at', 'full_url']


class LcpPageListSerializer(serializers.ModelSerializer):
    """Сокращённый сериализатор для списка страниц"""
    module_name = serializers.CharField(source='module.name', read_only=True)
    full_url = serializers.ReadOnlyField()
    
    class Meta:
        model = LcpPage
        fields = [
            'id', 'name', 'slug', 'module', 'module_name',
            'is_draft', 'is_template', 'is_homepage',
            'menu_order', 'show_in_menu', 'icon', 'full_url',
            'updated_at'
        ]


class LcpComponentCategorySerializer(serializers.ModelSerializer):
    components_count = serializers.SerializerMethodField()
    
    class Meta:
        model = LcpComponentCategory
        fields = ['id', 'name', 'slug', 'icon', 'order', 'components_count']
    
    def get_components_count(self, obj):
        return obj.components.filter(is_active=True).count()


class LcpComponentTemplateSerializer(serializers.ModelSerializer):
    category_name = serializers.CharField(source='category.name', read_only=True)
    module_name = serializers.CharField(source='module.name', read_only=True)
    
    class Meta:
        model = LcpComponentTemplate
        fields = [
            'id', 'name', 'category', 'category_name', 'component_type',
            'default_props', 'default_styles', 'default_classes', 'default_events',
            'children', 'icon', 'description', 'props_schema',
            'is_global', 'is_system', 'module', 'module_name', 'is_active',
            'created_at', 'updated_at'
        ]
        read_only_fields = ['created_at', 'updated_at']


class LcpComponentTemplateListSerializer(serializers.ModelSerializer):
    """Сокращённый для палитры"""
    category_name = serializers.CharField(source='category.name', read_only=True)
    
    class Meta:
        model = LcpComponentTemplate
        fields = [
            'id', 'name', 'category', 'category_name', 'component_type',
            'icon', 'description', 'is_global', 'is_system'
        ]


class LcpDataSourceSerializer(serializers.ModelSerializer):
    module_name = serializers.CharField(source='module.name', read_only=True)
    
    class Meta:
        model = LcpDataSource
        fields = [
            'id', 'name', 'slug', 'module', 'module_name', 'source_type',
            'config', 'default_params', 'cache_enabled', 'cache_ttl',
            'transform_enabled', 'transform_code', 'auto_refresh',
            'refresh_interval', 'description', 'is_active',
            'created_at', 'updated_at'
        ]
        read_only_fields = ['created_at', 'updated_at']


class LcpDatabaseTableSerializer(serializers.ModelSerializer):
    module_name = serializers.CharField(source='module.name', read_only=True)
    
    class Meta:
        model = LcpDatabaseTable
        fields = [
            'id', 'name', 'db_table_name', 'module', 'module_name',
            'schema', 'relations', 'indexes', 'is_migrated', 'last_migration',
            'description', 'created_at', 'updated_at'
        ]
        read_only_fields = ['created_at', 'updated_at', 'is_migrated', 'last_migration']


class LcpActionSerializer(serializers.ModelSerializer):
    module_name = serializers.CharField(source='module.name', read_only=True)
    
    class Meta:
        model = LcpAction
        fields = [
            'id', 'name', 'slug', 'module', 'module_name', 'action_type',
            'config', 'condition', 'requires_confirmation', 'confirmation_message',
            'description', 'is_active', 'created_at', 'updated_at'
        ]
        read_only_fields = ['created_at', 'updated_at']


class LcpVariableSerializer(serializers.ModelSerializer):
    module_name = serializers.CharField(source='module.name', read_only=True)
    
    class Meta:
        model = LcpVariable
        fields = [
            'id', 'name', 'module', 'module_name', 'scope', 'var_type',
            'default_value', 'persist', 'description'
        ]


class LcpAuditLogSerializer(serializers.ModelSerializer):
    user_name = serializers.CharField(source='user.username', read_only=True)
    content_type_name = serializers.CharField(source='content_type.model', read_only=True)
    
    class Meta:
        model = LcpAuditLog
        fields = [
            'id', 'content_type', 'content_type_name', 'object_id',
            'action', 'changes', 'snapshot', 'metadata',
            'user', 'user_name', 'ip_address', 'timestamp'
        ]
        read_only_fields = ['timestamp']


