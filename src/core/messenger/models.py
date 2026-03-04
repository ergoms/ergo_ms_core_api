from django.conf import settings
from django.contrib.contenttypes.fields import GenericForeignKey
from django.contrib.contenttypes.models import ContentType
from django.db import models


class Message(models.Model):
    MESSAGE_TYPES = (
        ('user', 'Пользовательское'),
        ('system', 'Системное'),
    )

    content_type = models.ForeignKey(
        ContentType,
        on_delete=models.CASCADE,
        verbose_name='Тип объекта',
    )
    object_id = models.PositiveIntegerField(verbose_name='ID объекта')
    content_object = GenericForeignKey('content_type', 'object_id')

    author = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        related_name='messenger_messages',
        verbose_name='Автор',
        null=True,
        blank=True,
    )
    reply_to = models.ForeignKey(
        'self',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='replies',
        verbose_name='Ответ на сообщение',
    )
    text = models.TextField(verbose_name='Текст сообщения', blank=True)
    message_type = models.CharField(
        max_length=10,
        choices=MESSAGE_TYPES,
        default='user',
        verbose_name='Тип сообщения',
    )
    is_edited = models.BooleanField(default=False, verbose_name='Редактировалось')
    created_at = models.DateTimeField(auto_now_add=True, db_index=True, verbose_name='Дата создания')
    updated_at = models.DateTimeField(auto_now=True, verbose_name='Дата обновления')

    class Meta:
        ordering = ['created_at']
        indexes = [
            models.Index(fields=['content_type', 'object_id', 'created_at']),
        ]
        verbose_name = 'Сообщение'
        verbose_name_plural = 'Сообщения'

    def __str__(self):
        return f'[{self.message_type}] {self.text[:50]}'


class MessageAttachment(models.Model):
    message = models.ForeignKey(
        Message,
        on_delete=models.CASCADE,
        related_name='attachments',
        verbose_name='Сообщение',
    )
    file = models.FileField(
        upload_to='messenger/attachments/%Y/%m/%d/',
        verbose_name='Файл',
    )
    original_filename = models.CharField(max_length=255, verbose_name='Оригинальное имя файла')
    file_size = models.PositiveIntegerField(default=0, verbose_name='Размер файла (байт)')
    mime_type = models.CharField(max_length=128, blank=True, verbose_name='MIME-тип')
    created_at = models.DateTimeField(auto_now_add=True, verbose_name='Дата загрузки')

    class Meta:
        ordering = ['created_at']
        verbose_name = 'Вложение сообщения'
        verbose_name_plural = 'Вложения сообщений'

    def __str__(self):
        return self.original_filename or f'Вложение #{self.pk}'

    def delete(self, using=None, keep_parents=False):
        storage = self.file.storage
        file_name = self.file.name
        result = super().delete(using=using, keep_parents=keep_parents)
        if file_name and storage.exists(file_name):
            storage.delete(file_name)
        return result
