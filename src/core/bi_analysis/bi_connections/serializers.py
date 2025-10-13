from rest_framework import serializers
from src.core.bi_analysis.bi_connections.models import Connection

class ConnectionSerializer(serializers.ModelSerializer):
    connector_type_display = serializers.CharField(source='get_connector_type_display', read_only=True)

    class Meta:
        model = Connection
        fields = [
            'id', 'name', 'connector_type', 'connector_type_display',
            'config', 'created_at', 'owner'
        ]
        read_only_fields = ['id', 'created_at', 'owner']

    def to_representation(self, instance):
        data = super().to_representation(instance)
        return data

    def update(self, instance, validated_data):
        config = validated_data.get('config', {})
        # Если пароль не передан — сохранить старый
        if 'password' not in config and 'config' in validated_data:
            config['password'] = instance.config.get('password')
        validated_data['config'] = config
        return super().update(instance, validated_data)

class CheckConnectionSerializer(serializers.Serializer):
    host = serializers.CharField()
    port = serializers.IntegerField()
    user = serializers.CharField()
    password = serializers.CharField()
    database = serializers.CharField(required=False, allow_blank=True)
    engine = serializers.ChoiceField(choices=["clickhouse", "postgresql", "mssql"])