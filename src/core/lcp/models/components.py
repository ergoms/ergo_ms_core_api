from django.db import models
from django.contrib.auth.models import User

from .modules import LcpModule


class LcpComponentCategory(models.Model):
    """Категория компонентов"""
    
    name = models.CharField(
        max_length=50,
        unique=True,
        verbose_name='Название'
    )
    slug = models.SlugField(
        max_length=50,
        unique=True,
        verbose_name='Slug'
    )
    icon = models.CharField(
        max_length=50,
        default='Folder',
        verbose_name='Иконка'
    )
    order = models.PositiveIntegerField(
        default=0,
        verbose_name='Порядок'
    )
    
    class Meta:
        ordering = ['order', 'name']
        verbose_name = 'Категория компонентов'
        verbose_name_plural = 'Категории компонентов'
    
    def __str__(self):
        return self.name


class LcpComponentTemplate(models.Model):
    """Сохранённый компонент для переиспользования"""
    
    name = models.CharField(
        max_length=100,
        verbose_name='Название'
    )
    category = models.ForeignKey(
        LcpComponentCategory,
        on_delete=models.SET_NULL,
        null=True,
        related_name='components',
        verbose_name='Категория'
    )
    
    # Базовый тип компонента
    component_type = models.CharField(
        max_length=50,
        verbose_name='Тип компонента'
    )
    
    # Свойства по умолчанию
    default_props = models.JSONField(
        default=dict,
        blank=True,
        verbose_name='Свойства по умолчанию'
    )
    
    # Стили по умолчанию
    default_styles = models.JSONField(
        default=dict,
        blank=True,
        verbose_name='Стили по умолчанию'
    )
    
    # CSS классы по умолчанию
    default_classes = models.JSONField(
        default=list,
        blank=True,
        verbose_name='CSS классы'
    )
    
    # События по умолчанию
    default_events = models.JSONField(
        default=list,
        blank=True,
        verbose_name='События'
    )
    
    # Вложенные компоненты (для составных)
    children = models.JSONField(
        default=list,
        blank=True,
        verbose_name='Вложенные компоненты'
    )
    
    # Метаданные для редактора
    icon = models.CharField(
        max_length=50,
        default='Box',
        verbose_name='Иконка'
    )
    description = models.TextField(
        blank=True,
        verbose_name='Описание'
    )
    
    # Настройки доступных свойств в редакторе
    props_schema = models.JSONField(
        default=dict,
        blank=True,
        verbose_name='Схема свойств'
    )
    
    # Доступность
    is_global = models.BooleanField(
        default=False,
        verbose_name='Глобальный (доступен всем модулям)'
    )
    is_system = models.BooleanField(
        default=False,
        verbose_name='Системный (нельзя удалить)'
    )
    module = models.ForeignKey(
        LcpModule,
        null=True,
        blank=True,
        on_delete=models.CASCADE,
        related_name='component_templates',
        verbose_name='Модуль'
    )
    
    is_active = models.BooleanField(
        default=True,
        verbose_name='Активен'
    )
    
    created_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        related_name='lcp_component_templates',
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
        ordering = ['category', 'name']
        verbose_name = 'Шаблон компонента'
        verbose_name_plural = 'Шаблоны компонентов'
    
    def __str__(self):
        return f'{self.name} ({self.component_type})'


