from django.db import models
from django.contrib.auth.models import User

from .modules import LcpModule


class LcpPage(models.Model):
    """Страница Low-Code платформы"""
    
    name = models.CharField(
        max_length=200,
        verbose_name='Название страницы'
    )
    slug = models.SlugField(
        max_length=100,
        verbose_name='Slug'
    )
    module = models.ForeignKey(
        LcpModule,
        on_delete=models.CASCADE,
        related_name='pages',
        verbose_name='Модуль'
    )
    
    # Дерево компонентов страницы
    component_tree = models.JSONField(
        default=list,
        blank=True,
        verbose_name='Дерево компонентов'
    )
    
    # Настройки страницы
    settings = models.JSONField(
        default=dict,
        blank=True,
        verbose_name='Настройки'
    )
    # settings: {title, description, layout, permissions}
    
    # Переменные страницы (локальный state)
    variables = models.JSONField(
        default=dict,
        blank=True,
        verbose_name='Переменные страницы'
    )
    
    # Источники данных страницы
    data_sources = models.JSONField(
        default=list,
        blank=True,
        verbose_name='Источники данных'
    )
    
    # Адаптивные настройки для разных breakpoints
    breakpoints = models.JSONField(
        default=dict,
        blank=True,
        verbose_name='Адаптивные настройки'
    )
    # breakpoints: {mobile: {...}, tablet: {...}, desktop: {...}}
    
    # Статусы
    is_draft = models.BooleanField(
        default=True,
        verbose_name='Черновик'
    )
    is_template = models.BooleanField(
        default=False,
        verbose_name='Шаблон'
    )
    is_homepage = models.BooleanField(
        default=False,
        verbose_name='Главная страница модуля'
    )
    
    # Порядок в навигации
    menu_order = models.PositiveIntegerField(
        default=0,
        verbose_name='Порядок в меню'
    )
    show_in_menu = models.BooleanField(
        default=True,
        verbose_name='Показывать в меню'
    )
    
    # Иконка для меню
    icon = models.CharField(
        max_length=50,
        blank=True,
        default='File',
        verbose_name='Иконка'
    )
    
    created_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        related_name='lcp_pages',
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
        ordering = ['module', 'menu_order', 'name']
        unique_together = ['module', 'slug']
        verbose_name = 'LCP Страница'
        verbose_name_plural = 'LCP Страницы'
    
    def __str__(self):
        return f'{self.module.name} / {self.name}'
    
    def save(self, *args, **kwargs):
        # Гарантируем единственную главную страницу в модуле
        if self.is_homepage:
            LcpPage.objects.filter(
                module=self.module,
                is_homepage=True
            ).exclude(pk=self.pk).update(is_homepage=False)
        super().save(*args, **kwargs)
    
    def get_full_url(self):
        """Полный URL страницы"""
        return f'/lcp/{self.module.slug}/{self.slug}'
    
    full_url = property(get_full_url)


