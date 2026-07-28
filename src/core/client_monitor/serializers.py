from rest_framework import serializers

from .models import ClientMonitorEvent, ClientMonitorSession


class ClientMonitorSessionListSerializer(serializers.ModelSerializer):
    class Meta:
        model = ClientMonitorSession
        fields = (
            'public_id',
            'user_public_id',
            'user_label',
            'user_agent',
            'language',
            'timezone',
            'viewport',
            'client_version',
            'started_at',
            'last_event_at',
            'has_errors',
            'event_count',
        )


class ClientMonitorSessionDetailSerializer(serializers.ModelSerializer):
    class Meta:
        model = ClientMonitorSession
        fields = (
            'public_id',
            'user_public_id',
            'user_label',
            'user_agent',
            'language',
            'timezone',
            'viewport',
            'client_version',
            'scope_claim_keys',
            'started_at',
            'last_event_at',
            'has_errors',
            'event_count',
        )


class ClientMonitorEventSerializer(serializers.ModelSerializer):
    class Meta:
        model = ClientMonitorEvent
        fields = (
            'id',
            'seq',
            'kind',
            'created_at',
            'received_at',
            'payload',
        )
