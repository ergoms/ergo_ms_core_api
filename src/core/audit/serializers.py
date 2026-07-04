from rest_framework import serializers

from . import catalog
from .models import AuditEvent


class AuditEventSerializer(serializers.ModelSerializer):
    """Запись журнала с обогащением из каталога действий."""

    actor_username = serializers.CharField(source='actor.username', default=None, read_only=True)
    action_label = serializers.SerializerMethodField()
    module_label = serializers.SerializerMethodField()
    category_label = serializers.SerializerMethodField()
    icon = serializers.SerializerMethodField()

    class Meta:
        model = AuditEvent
        ref_name = 'CoreAuditEvent'
        fields = (
            'id',
            'created_at',
            'actor',
            'actor_username',
            'actor_label',
            'source_module',
            'module_label',
            'action',
            'action_label',
            'category_label',
            'icon',
            'severity',
            'entity_type',
            'entity_ref',
            'entity_label',
            'changes',
            'meta',
            'organization_id',
            'department_id',
            'ip_address',
            'user_agent',
            'request_id',
        )
        read_only_fields = fields

    def _catalog(self):
        # Кешируем каталог на инстанс сериализатора (один запрос — один каталог).
        cache = getattr(self, '_catalog_cache', None)
        if cache is None:
            cache = catalog.get_catalog()
            self._catalog_cache = cache
        return cache

    def _section(self, obj):
        return self._catalog().get(obj.source_module or '')

    def _spec(self, obj):
        section = self._section(obj)
        if not section:
            return None
        return section['actions'].get(obj.action or '')

    def get_action_label(self, obj):
        spec = self._spec(obj)
        return spec['label'] if spec else obj.action

    def get_module_label(self, obj):
        section = self._section(obj)
        return section['module_label'] if section else obj.source_module

    def get_category_label(self, obj):
        spec = self._spec(obj)
        return spec['category_label'] if spec else ''

    def get_icon(self, obj):
        spec = self._spec(obj)
        return spec['icon'] if spec else ''
