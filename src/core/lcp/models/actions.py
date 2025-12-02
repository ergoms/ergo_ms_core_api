from django.db import models
from django.contrib.auth.models import User

from .modules import LcpModule


class LcpAction(models.Model):
    """Действие которое можно привязать к событию"""
    
    ACTION_TYPES = [
        ('api_call', 'API Call'),
        ('navigate', 'Navigate'),
        ('set_variable', 'Set Variable'),
        ('show_modal', 'Show Modal'),
        ('hide_modal', 'Hide Modal'),
        ('show_notification', 'Show Notification'),
        ('refresh_data', 'Refresh Data Source'),
        ('download', 'Download File'),
        ('copy_clipboard', 'Copy to Clipboard'),
        ('custom_js', 'Custom JavaScript'),
        ('chain', 'Chain Actions'),
        ('condition', 'Conditional Action'),
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
        related_name='actions',
        verbose_name='Модуль'
    )
    
    action_type = models.CharField(
        max_length=20,
        choices=ACTION_TYPES,
        verbose_name='Тип действия'
    )
    
    # Конфигурация действия
    config = models.JSONField(
        default=dict,
        verbose_name='Конфигурация'
    )
    
    # Условие выполнения
    condition = models.JSONField(
        null=True,
        blank=True,
        verbose_name='Условие'
    )
    
    # Подтверждение перед выполнением
    requires_confirmation = models.BooleanField(
        default=False,
        verbose_name='Требует подтверждения'
    )
    confirmation_message = models.CharField(
        max_length=200,
        blank=True,
        verbose_name='Сообщение подтверждения'
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
        related_name='lcp_actions',
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
        verbose_name = 'Действие'
        verbose_name_plural = 'Действия'
    
    def __str__(self):
        return f'{self.module.name} / {self.name}'


class LcpVariable(models.Model):
    """Переменная модуля или страницы"""
    
    SCOPES = [
        ('global', 'Global'),
        ('module', 'Module'),
        ('page', 'Page'),
        ('session', 'Session'),
    ]
    
    VAR_TYPES = [
        ('string', 'String'),
        ('number', 'Number'),
        ('boolean', 'Boolean'),
        ('array', 'Array'),
        ('object', 'Object'),
    ]
    
    name = models.CharField(
        max_length=100,
        verbose_name='Название'
    )
    module = models.ForeignKey(
        LcpModule,
        on_delete=models.CASCADE,
        related_name='variables',
        verbose_name='Модуль'
    )
    
    scope = models.CharField(
        max_length=20,
        choices=SCOPES,
        default='module',
        verbose_name='Область видимости'
    )
    
    var_type = models.CharField(
        max_length=20,
        choices=VAR_TYPES,
        default='string',
        verbose_name='Тип'
    )
    
    # Значение по умолчанию
    default_value = models.JSONField(
        null=True,
        blank=True,
        verbose_name='Значение по умолчанию'
    )
    
    # Persist в localStorage
    persist = models.BooleanField(
        default=False,
        verbose_name='Сохранять в localStorage'
    )
    
    description = models.TextField(
        blank=True,
        verbose_name='Описание'
    )
    
    class Meta:
        ordering = ['module', 'scope', 'name']
        unique_together = ['module', 'name']
        verbose_name = 'Переменная'
        verbose_name_plural = 'Переменные'
    
    def __str__(self):
        return f'{self.module.name} / {self.name}'


