from django.db import models

# CMSPage — активная модель (права на URL, синхронизация маршрутов).

PAGE_TYPE_WITH_LIMITATIONS = 'withliminations'
PAGE_TYPE_WITHOUT_LIMITATIONS = 'withoutliminations'
PAGE_TYPE_CLOSED = 'closepage'

PAGE_TYPE_CHOICES = [
    (PAGE_TYPE_WITH_LIMITATIONS, 'Страница с ограничениями'),
    (PAGE_TYPE_WITHOUT_LIMITATIONS, 'Страница без ограничений'),
    (PAGE_TYPE_CLOSED, 'Закрытая страница'),
]


class CMSPage(models.Model):
    path = models.CharField(max_length=255, default='')
    page_type = models.CharField(
        max_length=255,
        choices=PAGE_TYPE_CHOICES,
        default=PAGE_TYPE_WITHOUT_LIMITATIONS,
    )
