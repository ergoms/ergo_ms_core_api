"""История интервалов связи и leases отдельных вкладок."""
import uuid

from django.conf import settings
from django.db import models


class SessionConnectionInterval(models.Model):
    public_id = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    device_key = models.PositiveBigIntegerField()
    scope = models.JSONField(default=dict)
    scope_hash = models.CharField(max_length=64)
    device_name = models.CharField(max_length=100, blank=True)
    device_type = models.CharField(max_length=20, blank=True)
    browser = models.CharField(max_length=100, blank=True)
    os = models.CharField(max_length=100, blank=True)
    ip_address = models.GenericIPAddressField(null=True)
    started_at = models.DateTimeField()
    last_seen = models.DateTimeField()
    ended_at = models.DateTimeField(null=True)
    closed_at = models.DateTimeField(null=True)
    end_reason = models.CharField(max_length=24, blank=True)

    class Meta:
        app_label = 'cms_adp'
        indexes = [
            models.Index(fields=['scope_hash', 'user', '-last_seen'], name='adp_conn_scope_user_seen'),
            models.Index(fields=['closed_at'], name='adp_conn_closed'),
        ]
        constraints = [
            models.UniqueConstraint(fields=['user', 'device_key', 'scope_hash'],
                                    condition=models.Q(closed_at__isnull=True), name='adp_conn_one_open'),
        ]


class PresenceConnection(models.Model):
    connection_id = models.UUIDField()
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    device_key = models.PositiveBigIntegerField()
    scope_hash = models.CharField(max_length=64)
    interval = models.ForeignKey(SessionConnectionInterval, on_delete=models.CASCADE, related_name='connections', null=True)
    last_seen = models.DateTimeField()
    is_active = models.BooleanField(default=True)
    is_terminal = models.BooleanField(default=False)

    class Meta:
        app_label = 'cms_adp'
        constraints = [
            models.UniqueConstraint(fields=['connection_id', 'user', 'scope_hash'], name='adp_conn_tab_interval'),
        ]
        indexes = [
            models.Index(fields=['connection_id'], name='adp_conn_tab_id'),
        ]
