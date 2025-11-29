"""
Модели для управления боковым меню.
"""

from django.db import models
from django.contrib.auth.models import User
from django.db.models import Max

from src.core.cms.adp.models import Role, RoleGroup


class MenuItem(models.Model):
    """
    Элемент бокового меню.
    Поддерживает иерархическую структуру через parent.
    """
    ITEM_TYPES = [
        ('route', 'Маршрут Vue'),
        ('group', 'Группа'),
        ('offcanvas', 'Боковая панель'),
        ('external', 'Внешняя ссылка'),
    ]
    
    name = models.CharField(max_length=100, verbose_name='Название')
    route_name = models.CharField(
        max_length=100, 
        blank=True, 
        null=True, 
        verbose_name='Имя маршрута Vue',
        help_text='Имя маршрута из Vue Router (например: User, Settings, BI)'
    )
    icon = models.CharField(
        max_length=50, 
        blank=True, 
        null=True, 
        verbose_name='Иконка',
        help_text='Название иконки из Lucide (например: CircleUserRound, UserCog)'
    )
    item_type = models.CharField(
        max_length=20, 
        choices=ITEM_TYPES, 
        default='route', 
        verbose_name='Тип элемента'
    )
    
    # Для offcanvas элементов
    page = models.CharField(
        max_length=50, 
        blank=True, 
        null=True, 
        verbose_name='Страница боковой панели',
        help_text='Для BI модуля: datasets, connections, charts, dashboards'
    )
    
    # Для внешних ссылок
    external_url = models.URLField(
        blank=True, 
        null=True, 
        verbose_name='Внешняя ссылка'
    )
    
    # Иерархия
    parent = models.ForeignKey(
        'self',
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name='children',
        verbose_name='Родительский элемент'
    )
    
    # Порядок отображения (автоматически вычисляется если не указан)
    order = models.PositiveIntegerField(
        null=True, 
        blank=True, 
        verbose_name='Порядок',
        help_text='Оставьте пустым для автоматического определения'
    )
    
    # Доступ
    is_active = models.BooleanField(default=True, verbose_name='Активен')
    is_admin_only = models.BooleanField(
        default=False, 
        verbose_name='Только для администраторов'
    )
    
    # Связь с ролями для доступа
    allowed_roles = models.ManyToManyField(
        Role,
        blank=True,
        related_name='menu_items',
        verbose_name='Разрешённые роли',
        help_text='Если не выбрано ни одной роли, доступно всем'
    )
    
    # Связь с ролевыми группами для доступа
    allowed_role_groups = models.ManyToManyField(
        RoleGroup,
        blank=True,
        related_name='menu_items',
        verbose_name='Разрешённые ролевые группы'
    )
    
    # Модуль-источник (для автоматического определения)
    module_source = models.CharField(
        max_length=100, 
        blank=True, 
        null=True, 
        verbose_name='Модуль-источник',
        help_text='Путь к модулю (например: core/cms, modules/bi)'
    )
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        app_label = 'cms_adp'
        verbose_name = 'Элемент меню'
        verbose_name_plural = 'Элементы меню'
        ordering = ['order', 'name']
    
    def __str__(self):
        if self.parent:
            return f"{self.parent.name} > {self.name}"
        return self.name
    
    def save(self, *args, **kwargs):
        # Автоматически присваиваем порядок, если не указан
        if self.order is None:
            max_order = MenuItem.objects.filter(
                parent=self.parent
            ).aggregate(Max('order'))['order__max']
            self.order = (max_order or 0) + 10
        super().save(*args, **kwargs)
    
    @classmethod
    def get_next_order(cls, parent=None):
        """Возвращает следующий порядок для указанного родителя."""
        max_order = cls.objects.filter(parent=parent).aggregate(Max('order'))['order__max']
        return (max_order or 0) + 10
    
    def get_children_tree(self):
        """Рекурсивно получает все дочерние элементы"""
        children = []
        for child in self.children.filter(is_active=True).order_by('order'):
            child_data = {
                'id': child.id,
                'name': child.name,
                'route_name': child.route_name,
                'icon': child.icon,
                'item_type': child.item_type,
                'page': child.page,
                'order': child.order,
                'children': child.get_children_tree()
            }
            children.append(child_data)
        return children


class MenuSeparator(models.Model):
    """
    Разделитель в меню.
    Отображается перед элементом меню с указанным порядком.
    """
    name = models.CharField(max_length=100, verbose_name='Название разделителя')
    before_order = models.PositiveIntegerField(
        verbose_name='Перед порядком',
        help_text='Разделитель будет отображаться перед элементами с этим порядком'
    )
    
    is_active = models.BooleanField(default=True, verbose_name='Активен')
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        app_label = 'cms_adp'
        verbose_name = 'Разделитель меню'
        verbose_name_plural = 'Разделители меню'
        ordering = ['before_order']
    
    def __str__(self):
        return f"{self.name} (перед {self.before_order})"


class MenuAccessLog(models.Model):
    """
    Лог доступа к элементам меню.
    Для аналитики и аудита.
    """
    user = models.ForeignKey(
        User, 
        on_delete=models.CASCADE, 
        related_name='menu_access_logs',
        verbose_name='Пользователь'
    )
    menu_item = models.ForeignKey(
        MenuItem, 
        on_delete=models.CASCADE, 
        related_name='access_logs',
        verbose_name='Элемент меню'
    )
    accessed_at = models.DateTimeField(auto_now_add=True, verbose_name='Время доступа')
    
    class Meta:
        app_label = 'cms_adp'
        verbose_name = 'Лог доступа к меню'
        verbose_name_plural = 'Логи доступа к меню'
        ordering = ['-accessed_at']
    
    def __str__(self):
        return f"{self.user.username} -> {self.menu_item.name} ({self.accessed_at})"

