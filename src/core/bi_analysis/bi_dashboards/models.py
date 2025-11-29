from django.db import models
from django.contrib.auth import get_user_model
from django.conf import settings

JSONField = models.JSONField


class Dashboard(models.Model):
    """
    Модель дашборда - контейнер для страниц с элементами визуализации.
    """
    name = models.CharField(max_length=255, verbose_name='Название')
    description = models.TextField(blank=True, default='', verbose_name='Описание')
    owner = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='dashboards',
        verbose_name='Владелец'
    )
    created_at = models.DateTimeField(auto_now_add=True, verbose_name='Создан')
    updated_at = models.DateTimeField(auto_now=True, verbose_name='Обновлен')

    class Meta:
        verbose_name = 'Дашборд'
        verbose_name_plural = 'Дашборды'
        ordering = ['-created_at']

    def __str__(self):
        return self.name

    @property
    def charts_count(self):
        """Количество чартов, используемых в дашборде."""
        chart_ids = set()
        for page in self.pages.all():
            for item in page.items.all():
                if item.type == 'Чарт' and item.config:
                    charts_list = item.config.get('chartsList', [])
                    for chart_data in charts_list:
                        if isinstance(chart_data, dict) and 'id' in chart_data:
                            chart_ids.add(chart_data['id'])
                        elif isinstance(chart_data, int):
                            chart_ids.add(chart_data)
        return len(chart_ids)


class DashboardPage(models.Model):
    """
    Модель страницы дашборда - контейнер для элементов на странице.
    """
    dashboard = models.ForeignKey(
        Dashboard,
        on_delete=models.CASCADE,
        related_name='pages',
        verbose_name='Дашборд'
    )
    name = models.CharField(max_length=255, verbose_name='Название страницы')
    order = models.PositiveIntegerField(default=0, verbose_name='Порядок')

    class Meta:
        verbose_name = 'Страница дашборда'
        verbose_name_plural = 'Страницы дашборда'
        ordering = ['order', 'id']
        unique_together = [['dashboard', 'order']]

    def __str__(self):
        return f"{self.dashboard.name} - {self.name}"


class DashboardItem(models.Model):
    """
    Модель элемента дашборда - заголовок, текст, чарт или селектор.
    """
    ITEM_TYPE_CHOICES = [
        ('Заголовок', 'Заголовок'),
        ('Текст', 'Текст'),
        ('Чарт', 'Чарт'),
        ('Селектор', 'Селектор'),
    ]

    page = models.ForeignKey(
        DashboardPage,
        on_delete=models.CASCADE,
        related_name='items',
        verbose_name='Страница'
    )
    type = models.CharField(
        max_length=50,
        choices=ITEM_TYPE_CHOICES,
        verbose_name='Тип элемента'
    )
    # Позиция и размер элемента
    x = models.IntegerField(default=0, verbose_name='Позиция X')
    y = models.IntegerField(default=0, verbose_name='Позиция Y')
    width = models.IntegerField(default=200, verbose_name='Ширина')
    height = models.IntegerField(default=150, verbose_name='Высота')
    # Конфигурация элемента (JSON с настройками)
    config = models.JSONField(default=dict, blank=True, verbose_name='Конфигурация')
    # Порядок отображения
    order = models.PositiveIntegerField(default=0, verbose_name='Порядок')

    class Meta:
        verbose_name = 'Элемент дашборда'
        verbose_name_plural = 'Элементы дашборда'
        ordering = ['order', 'id']

    def __str__(self):
        return f"{self.page.dashboard.name} - {self.type}"

