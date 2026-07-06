from django.conf import settings
from django.db import models


class AuditEvent(models.Model):
    """Append-only запись о действии пользователя в системе.

    Единая модель для всего приложения: ядро и модули пишут сюда через
    ModuleBridge (`audit.record`) или через `AuditedModelViewSet`. Модули
    не импортируют эту модель напрямую.
    """

    SEVERITY_INFO = 'info'
    SEVERITY_SECURITY = 'security'
    SEVERITY_CRITICAL = 'critical'
    SEVERITY_CHOICES = (
        (SEVERITY_INFO, 'Информация'),
        (SEVERITY_SECURITY, 'Безопасность'),
        (SEVERITY_CRITICAL, 'Критично'),
    )

    created_at = models.DateTimeField(
        auto_now_add=True,
        db_index=True,
        verbose_name='Время',
    )
    actor = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='audit_events',
        verbose_name='Инициатор',
    )
    # Снимок отображаемого имени на момент события — чтобы лента не ломалась
    # при удалении/переименовании пользователя.
    actor_label = models.CharField(
        max_length=255,
        blank=True,
        default='',
        verbose_name='Инициатор (снимок)',
    )
    source_module = models.CharField(
        max_length=64,
        blank=True,
        default='',
        db_index=True,
        verbose_name='Модуль-источник',
    )
    action = models.CharField(
        max_length=128,
        db_index=True,
        verbose_name='Действие',
    )
    severity = models.CharField(
        max_length=16,
        choices=SEVERITY_CHOICES,
        default=SEVERITY_INFO,
        verbose_name='Важность',
    )
    entity_type = models.CharField(
        max_length=64,
        blank=True,
        default='',
        verbose_name='Тип объекта',
    )
    # Публичная непредсказуемая ссылка на объект (public_id/UUID), не pk БД.
    entity_ref = models.CharField(
        max_length=128,
        blank=True,
        default='',
        verbose_name='Ссылка на объект',
    )
    entity_label = models.CharField(
        max_length=255,
        blank=True,
        default='',
        verbose_name='Объект (снимок)',
    )
    # Список изменений полей: [{'field', 'label', 'old', 'new'}]
    changes = models.JSONField(
        null=True,
        blank=True,
        verbose_name='Изменения',
    )
    meta = models.JSONField(
        default=dict,
        blank=True,
        verbose_name='Метаданные',
    )
    organization_id = models.PositiveBigIntegerField(
        null=True,
        blank=True,
        db_index=True,
        verbose_name='Организация',
    )
    department_id = models.PositiveBigIntegerField(
        null=True,
        blank=True,
        verbose_name='Подразделение',
    )
    ip_address = models.GenericIPAddressField(
        null=True,
        blank=True,
        verbose_name='IP-адрес',
    )
    user_agent = models.CharField(
        max_length=512,
        blank=True,
        default='',
        verbose_name='User-Agent',
    )
    request_id = models.CharField(
        max_length=64,
        blank=True,
        default='',
        verbose_name='ID запроса',
    )

    class Meta:
        app_label = 'core_audit'
        verbose_name = 'Запись журнала действий'
        verbose_name_plural = 'Журнал действий'
        ordering = ['-created_at', '-id']
        indexes = [
            models.Index(fields=['source_module', 'action', 'created_at']),
            models.Index(fields=['actor', 'created_at']),
            models.Index(fields=['organization_id', 'created_at']),
            models.Index(fields=['entity_type', 'entity_ref']),
        ]

    def __str__(self):
        return f'{self.action} by {self.actor_label or self.actor_id} @ {self.created_at:%d.%m.%Y %H:%M}'


class AuditActor(models.Model):
    """Справочник инициаторов для фильтра UI (обновляется при записи событий)."""

    filter_value = models.CharField(
        max_length=128,
        unique=True,
        verbose_name='Значение фильтра',
    )
    label = models.CharField(
        max_length=255,
        verbose_name='Отображаемое имя',
    )
    actor = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='audit_actor_entries',
        verbose_name='Пользователь',
    )
    last_seen_at = models.DateTimeField(
        auto_now=True,
        verbose_name='Последнее событие',
    )

    class Meta:
        app_label = 'core_audit'
        verbose_name = 'Инициатор журнала'
        verbose_name_plural = 'Инициаторы журнала'
        ordering = ['label']

    def __str__(self):
        return self.label or self.filter_value
