from rest_framework import serializers

from .models import Notification


class NotificationSerializer(serializers.ModelSerializer):
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
