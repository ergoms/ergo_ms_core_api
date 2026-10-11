from rest_framework import serializers

from . import catalog
from .models import Notification
from .scope import resolve_scope_labels


class NotificationSerializer(serializers.ModelSerializer):
    module_label = serializers.SerializerMethodField()
    event_label = serializers.SerializerMethodField()
    category_label = serializers.SerializerMethodField()
    scope_label = serializers.SerializerMethodField()

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
            'event_label',
            'category_label',
            'scope_ref',
            'scope_label',
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

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        instance = args[0] if args else kwargs.get('instance')
        missing = []
        if instance is None:
            self.context.setdefault('_scope_labels', {})
            return
        rows = instance if self._is_many(instance) else [instance]
        for row in rows:
            ref = getattr(row, 'scope_ref', '') or ''
            label = (getattr(row, 'scope_label', '') or '').strip()
            if ref and not label:
                missing.append(ref)
        self.context['_scope_labels'] = resolve_scope_labels(missing)

    @staticmethod
    def _is_many(instance) -> bool:
        if isinstance(instance, (list, tuple)):
            return True
        return hasattr(instance, '__iter__') and not isinstance(instance, Notification)

    def _catalog(self):
        cache = getattr(self, '_catalog_cache', None)
        if cache is None:
            cache = catalog.get_catalog()
            self._catalog_cache = cache
        return cache

    def _event_spec(self, obj):
        section = self._catalog().get(obj.source_module or '')
        if not section:
            return None
        return section['events'].get(obj.event_key or '')

    def get_module_label(self, obj):
        key = obj.source_module or ''
        if not key:
            return ''
        section = self._catalog().get(key)
        return section['module_label'] if section else key

    def get_event_label(self, obj):
        spec = self._event_spec(obj)
        if not spec:
            return ''
        return spec.get('label') or ''

    def get_category_label(self, obj):
        spec = self._event_spec(obj)
        if not spec:
            return ''
        return spec.get('category_label') or ''

    def get_scope_label(self, obj):
        stored = (getattr(obj, 'scope_label', '') or '').strip()
        if stored:
            return stored
        ref = getattr(obj, 'scope_ref', '') or ''
        if not ref:
            return ''
        return (self.context.get('_scope_labels') or {}).get(ref, '')
