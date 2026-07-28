import uuid

from django.conf import settings
from django.db import models


class ClientMonitorSession(models.Model):
    """Сессия мониторинга SPA-клиента (correlation id с клиента)."""

    public_id = models.UUIDField(
        default=uuid.uuid4,
        unique=True,
        editable=False,
        db_index=True,
        verbose_name='ID сессии',
    )
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='client_monitor_sessions',
        verbose_name='Пользователь',
    )
    user_public_id = models.CharField(
        max_length=64,
        blank=True,
        default='',
        db_index=True,
        verbose_name='public_id пользователя',
    )
    user_label = models.CharField(
        max_length=255,
        blank=True,
        default='',
        verbose_name='Пользователь (снимок)',
    )
    user_agent = models.TextField(blank=True, default='', verbose_name='User-Agent')
    language = models.CharField(max_length=32, blank=True, default='', verbose_name='Язык')
    timezone = models.CharField(max_length=64, blank=True, default='', verbose_name='Часовой пояс')
    viewport = models.CharField(max_length=32, blank=True, default='', verbose_name='Viewport')
    client_version = models.CharField(
        max_length=64,
        blank=True,
        default='',
        verbose_name='Версия клиента',
    )
    scope_claim_keys = models.JSONField(
        default=list,
        blank=True,
        verbose_name='Ключи session-scope claims',
    )
    started_at = models.DateTimeField(auto_now_add=True, db_index=True, verbose_name='Начало')
    last_event_at = models.DateTimeField(auto_now_add=True, db_index=True, verbose_name='Последнее событие')
    has_errors = models.BooleanField(default=False, db_index=True, verbose_name='Есть ошибки')
    event_count = models.PositiveIntegerField(default=0, verbose_name='Число событий')

    class Meta:
        verbose_name = 'Сессия мониторинга клиента'
        verbose_name_plural = 'Сессии мониторинга клиентов'
        ordering = ['-last_event_at']
        indexes = [
            models.Index(
                fields=['has_errors', '-last_event_at'],
                name='cm_sess_err_last_idx',
            ),
            models.Index(
                fields=['user', '-last_event_at'],
                name='cm_sess_user_last_idx',
            ),
        ]

    def __str__(self):
        return f'{self.public_id} ({self.user_label or self.user_public_id or "-"})'


class ClientMonitorEvent(models.Model):
    """Одно событие следа клиента внутри сессии мониторинга."""

    KIND_NAV = 'nav'
    KIND_API = 'api'
    KIND_ERROR = 'error'
    KIND_WARN = 'warn'
    KIND_LIFECYCLE = 'lifecycle'
    KIND_CHOICES = (
        (KIND_NAV, 'Навигация'),
        (KIND_API, 'API'),
        (KIND_ERROR, 'Ошибка'),
        (KIND_WARN, 'Предупреждение'),
        (KIND_LIFECYCLE, 'Жизненный цикл'),
    )

    session = models.ForeignKey(
        ClientMonitorSession,
        on_delete=models.CASCADE,
        related_name='events',
        verbose_name='Сессия',
    )
    seq = models.PositiveIntegerField(verbose_name='Порядковый номер')
    kind = models.CharField(max_length=16, choices=KIND_CHOICES, db_index=True, verbose_name='Тип')
    created_at = models.DateTimeField(db_index=True, verbose_name='Время клиента')
    received_at = models.DateTimeField(auto_now_add=True, db_index=True, verbose_name='Время приёма')
    payload = models.JSONField(default=dict, blank=True, verbose_name='Данные')

    class Meta:
        verbose_name = 'Событие мониторинга клиента'
        verbose_name_plural = 'События мониторинга клиентов'
        ordering = ['session_id', 'seq']
        constraints = [
            models.UniqueConstraint(
                fields=['session', 'seq'],
                name='cm_event_session_seq_uniq',
            ),
        ]
        indexes = [
            models.Index(
                fields=['session', 'seq'],
                name='cm_event_sess_seq_idx',
            ),
            models.Index(
                fields=['kind', 'created_at'],
                name='cm_event_kind_created_idx',
            ),
            models.Index(
                fields=['created_at'],
                name='cm_event_created_idx',
            ),
        ]

    def __str__(self):
        return f'{self.kind}#{self.seq} @ {self.created_at}'
