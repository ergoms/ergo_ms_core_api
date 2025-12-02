from django.db import models
from django.contrib.auth.models import User

from .modules import LcpModule


class LcpDataSource(models.Model):
    """Источник данных"""
    
    SOURCE_TYPES = [
        ('api', 'API Endpoint'),
        ('sql', 'SQL Query'),
        ('table', 'Database Table'),
        ('external', 'External API'),
        ('static', 'Static JSON'),
        ('websocket', 'WebSocket'),
    ]
    
    name = models.CharField(
        max_length=100,
        verbose_name='Название'
    )
    slug = models.SlugField(
        max_length=100,
        verbose_name='Slug'
    )
    module = models.ForeignKey(
        LcpModule,
        on_delete=models.CASCADE,
        related_name='data_sources',
        verbose_name='Модуль'
    )
    
    source_type = models.CharField(
        max_length=20,
        choices=SOURCE_TYPES,
        verbose_name='Тип источника'
    )
    
    # Конфигурация источника
    config = models.JSONField(
        default=dict,
        verbose_name='Конфигурация'
    )
    
    # Параметры запроса (могут переопределяться)
    default_params = models.JSONField(
        default=dict,
        blank=True,
        verbose_name='Параметры по умолчанию'
    )
    
    # Кеширование
    cache_enabled = models.BooleanField(
        default=False,
        verbose_name='Кеширование включено'
    )
    cache_ttl = models.PositiveIntegerField(
        default=60,
        verbose_name='TTL кеша (секунды)'
    )
    
    # Трансформация данных (JS код)
    transform_enabled = models.BooleanField(
        default=False,
        verbose_name='Трансформация включена'
    )
    transform_code = models.TextField(
        blank=True,
        verbose_name='Код трансформации'
    )
    
    # Автообновление
    auto_refresh = models.BooleanField(
        default=False,
        verbose_name='Автообновление'
    )
    refresh_interval = models.PositiveIntegerField(
        default=30,
        verbose_name='Интервал обновления (секунды)'
    )
    
    description = models.TextField(
        blank=True,
        verbose_name='Описание'
    )
    
    is_active = models.BooleanField(
        default=True,
        verbose_name='Активен'
    )
    
    created_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        related_name='lcp_data_sources',
        verbose_name='Создатель'
    )
    created_at = models.DateTimeField(
        auto_now_add=True,
        verbose_name='Дата создания'
    )
    updated_at = models.DateTimeField(
        auto_now=True,
        verbose_name='Дата обновления'
    )
    
    class Meta:
        ordering = ['module', 'name']
        unique_together = ['module', 'slug']
        verbose_name = 'Источник данных'
        verbose_name_plural = 'Источники данных'
    
    def __str__(self):
        return f'{self.module.name} / {self.name}'


class LcpDatabaseTable(models.Model):
    """Таблица БД созданная визуально"""
    
    name = models.CharField(
        max_length=100,
        verbose_name='Название таблицы'
    )
    db_table_name = models.CharField(
        max_length=100,
        unique=True,
        verbose_name='Имя в БД'
    )
    module = models.ForeignKey(
        LcpModule,
        on_delete=models.CASCADE,
        related_name='database_tables',
        verbose_name='Модуль'
    )
    
    # Схема таблицы
    schema = models.JSONField(
        default=list,
        verbose_name='Схема'
    )
    
    # Связи с другими таблицами
    relations = models.JSONField(
        default=list,
        blank=True,
        verbose_name='Связи'
    )
    
    # Индексы
    indexes = models.JSONField(
        default=list,
        blank=True,
        verbose_name='Индексы'
    )
    
    # Статус миграции
    is_migrated = models.BooleanField(
        default=False,
        verbose_name='Миграция применена'
    )
    last_migration = models.CharField(
        max_length=100,
        blank=True,
        verbose_name='Последняя миграция'
    )
    
    description = models.TextField(
        blank=True,
        verbose_name='Описание'
    )
    
    created_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        related_name='lcp_database_tables',
        verbose_name='Создатель'
    )
    created_at = models.DateTimeField(
        auto_now_add=True,
        verbose_name='Дата создания'
    )
    updated_at = models.DateTimeField(
        auto_now=True,
        verbose_name='Дата обновления'
    )
    
    class Meta:
        ordering = ['module', 'name']
        verbose_name = 'Таблица БД'
        verbose_name_plural = 'Таблицы БД'
    
    def __str__(self):
        return f'{self.module.name} / {self.name}'


