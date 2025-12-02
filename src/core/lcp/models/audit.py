from django.db import models
from django.contrib.auth.models import User
from django.contrib.contenttypes.fields import GenericForeignKey
from django.contrib.contenttypes.models import ContentType


class LcpAuditLog(models.Model):
    """История изменений"""
    
    ACTIONS = [
        ('create', 'Create'),
        ('update', 'Update'),
        ('delete', 'Delete'),
        ('publish', 'Publish'),
        ('revert', 'Revert'),
    ]
    
    # Generic FK для любой модели LCP
    content_type = models.ForeignKey(
        ContentType,
        on_delete=models.CASCADE,
        verbose_name='Тип объекта'
    )
    object_id = models.PositiveIntegerField(
        verbose_name='ID объекта'
    )
    content_object = GenericForeignKey('content_type', 'object_id')
    
    # Действие
    action = models.CharField(
        max_length=20,
        choices=ACTIONS,
        verbose_name='Действие'
    )
    
    # Что изменилось (diff)
    changes = models.JSONField(
        default=dict,
        blank=True,
        verbose_name='Изменения'
    )
    
    # Полный снимок для отката
    snapshot = models.JSONField(
        null=True,
        blank=True,
        verbose_name='Снимок'
    )
    
    # Дополнительные данные
    metadata = models.JSONField(
        default=dict,
        blank=True,
        verbose_name='Метаданные'
    )
    
    # Кто и когда
    user = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        related_name='lcp_audit_logs',
        verbose_name='Пользователь'
    )
    ip_address = models.GenericIPAddressField(
        null=True,
        blank=True,
        verbose_name='IP адрес'
    )
    user_agent = models.CharField(
        max_length=500,
        blank=True,
        verbose_name='User Agent'
    )
    timestamp = models.DateTimeField(
        auto_now_add=True,
        verbose_name='Время'
    )
    
    class Meta:
        ordering = ['-timestamp']
        indexes = [
            models.Index(fields=['content_type', 'object_id', '-timestamp']),
            models.Index(fields=['user', '-timestamp']),
            models.Index(fields=['-timestamp']),
        ]
        verbose_name = 'Запись аудита'
        verbose_name_plural = 'Записи аудита'
    
    def __str__(self):
        return f'{self.action} {self.content_type} #{self.object_id}'


