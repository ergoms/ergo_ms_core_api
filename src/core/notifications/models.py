from django.conf import settings
from django.db import models
from django.db.models import Q


class Notification(models.Model):
    LEVEL_INFO = 'info'
    LEVEL_SUCCESS = 'success'
    LEVEL_WARNING = 'warning'
    LEVEL_ERROR = 'error'
    LEVEL_CHOICES = (
        (LEVEL_INFO, 'Информация'),
        (LEVEL_SUCCESS, 'Успех'),
        (LEVEL_WARNING, 'Предупреждение'),
        (LEVEL_ERROR, 'Ошибка'),
    )

    recipient = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='core_inbox_notifications',
        verbose_name='Получатель',
    )
    title = models.CharField(max_length=255, verbose_name='Заголовок')
    body = models.TextField(blank=True, default='', verbose_name='Текст')
    level = models.CharField(
        max_length=16,
        choices=LEVEL_CHOICES,
        default=LEVEL_INFO,
        verbose_name='Тип',
    )
    icon = models.CharField(
        max_length=64,
        blank=True,
        default='',
        verbose_name='Имя иконки',
    )
    source_module = models.CharField(
        max_length=64,
        blank=True,
        default='',
        verbose_name='Модуль-источник',
    )
    event_key = models.CharField(
        max_length=128,
        blank=True,
        default='',
        verbose_name='Ключ события',
    )
    link_url = models.CharField(
        max_length=512,
        blank=True,
        default='',
        verbose_name='URL для перехода',
    )
    route = models.JSONField(
        blank=True,
        null=True,
        verbose_name='Vue Router (name + params)',
    )
    meta = models.JSONField(
        blank=True,
        default=dict,
        verbose_name='Доп. данные',
    )
    idempotency_key = models.CharField(
        max_length=255,
        blank=True,
        null=True,
        verbose_name='Ключ идемпотентности',
    )
    is_read = models.BooleanField(default=False, verbose_name='Прочитано')
    created_at = models.DateTimeField(auto_now_add=True, db_index=True, verbose_name='Создано')
    read_at = models.DateTimeField(blank=True, null=True, verbose_name='Прочитано в')

    class Meta:
        ordering = ['-created_at']
        verbose_name = 'Уведомление'
        verbose_name_plural = 'Уведомления'
        indexes = [
            models.Index(
                fields=['recipient', 'is_read', 'created_at'],
                name='core_notif_recipient_idx',
            ),
        ]
        constraints = [
            models.UniqueConstraint(
                fields=['recipient', 'idempotency_key'],
                name='uniq_recipient_idem',
                condition=Q(idempotency_key__isnull=False),
            ),
        ]

    def __str__(self):
        return f'[{self.level}] {self.title} -> user_id={self.recipient_id}'
