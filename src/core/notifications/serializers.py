from rest_framework import serializers

from . import catalog
from .models import Notification


class NotificationSerializer(serializers.ModelSerializer):
    module_label = serializers.SerializerMethodField()

    class Meta:
        model = Notification
        ref_name = 'CoreNotification'
        fields = (
            'id',
            'title',
            'body',
            'level',
            'icon',
            'source_module',
            'module_label',
            'event_key',
            'link_url',
            'route',
            'meta',
            'actions',
            'actions_state',
            'resolved_action_id',
            'resolved_at',
            'is_read',
            'archived_at',
            'deleted_at',
            'sidebar_hidden_at',
            'created_at',
            'read_at',
        )
        read_only_fields = fields

    def _catalog(self):
        cache = getattr(self, '_catalog_cache', None)
        if cache is None:
            cache = catalog.get_catalog()
            self._catalog_cache = cache
        return cache

    def get_module_label(self, obj):
        key = obj.source_module or ''
        if not key:
            return ''
        section = self._catalog().get(key)
        return section['module_label'] if section else key
