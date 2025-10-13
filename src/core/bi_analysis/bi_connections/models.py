from django.db import models
from django.contrib.auth import get_user_model

class Connection(models.Model):
    CONNECTOR_TYPE_CHOICES = [
        ('postgres', 'PostgreSQL'),
        ('clickhouse', 'ClickHouse'),
        ('mssql', 'Microsoft SQL Server'),
        ('file', 'Файл'),
    ]

    name = models.CharField(max_length=255)
    connector_type = models.CharField(max_length=50, choices=CONNECTOR_TYPE_CHOICES)
    config = models.JSONField()  # например: {"host": "...", "port": "...", "user": "..."}
    created_at = models.DateTimeField(auto_now_add=True)
    owner = models.ForeignKey(get_user_model(), on_delete=models.CASCADE, related_name='connections')

    def __str__(self):
        return f"{self.name} ({self.get_connector_type_display()})"