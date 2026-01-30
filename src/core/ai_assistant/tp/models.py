from django.db import models
from django.contrib.auth import get_user_model
import uuid

User = get_user_model()


def tp_document_upload_to(instance, filename):
    return f'tp_documents/{instance.id}.docx'


class TechnologicalProcessDocument(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='tp_documents')
    session = models.ForeignKey(
        'ai_assistant.ChatSession',
        on_delete=models.CASCADE,
        related_name='tp_documents',
        help_text='Сессия чата, к которой привязан документ',
        null=True,
        blank=True,
    )
    title = models.CharField(max_length=500, help_text='Название документа техпроцесса')
    file = models.FileField(
        upload_to=tp_document_upload_to,
        help_text='Оригинальный файл техпроцесса (DOCX)'
    )
    file_type = models.CharField(
        max_length=50,
        default='docx',
        help_text='Тип файла (обычно docx)'
    )
    markdown_content = models.TextField(
        help_text='Конвертированный Markdown контент документа'
    )
    metadata = models.JSONField(default=dict, blank=True, help_text='Дополнительные метаданные документа')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'ai_assistant_technologicalprocessdocument'
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['user', '-created_at']),
            models.Index(fields=['session', '-created_at']),
        ]
        verbose_name = 'Документ техпроцесса'
        verbose_name_plural = 'Документы техпроцессов'

    def __str__(self):
        return f"{self.title} ({self.user.username})"
