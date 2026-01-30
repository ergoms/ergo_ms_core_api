from django.db import models
from django.contrib.auth import get_user_model
from django.contrib.postgres.fields import ArrayField
import uuid

User = get_user_model()


class ChatSession(models.Model):
    """
    Сессия чата - представляет один разговор с AI ассистентом
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='chat_sessions')
    title = models.CharField(max_length=255, blank=True, null=True)
    module = models.CharField(max_length=50, default='chat', help_text='Модуль AI ассистента (chat, bi, etc.)')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    # Метаданные для BI модуля (file_id для связи с файлом)
    metadata = models.JSONField(default=dict, blank=True, help_text='Дополнительные данные сессии (file_id для BI и т.д.)')
    
    class Meta:
        ordering = ['-updated_at']
        indexes = [
            models.Index(fields=['user', '-updated_at']),
            models.Index(fields=['user', 'module', '-updated_at']),
        ]
    
    def __str__(self):
        return f"{self.user.username} - {self.title or 'Без названия'} ({self.module})"
    
    @property
    def message_count(self):
        return self.messages.count()


class ChatMessage(models.Model):
    """
    Сообщение в чате - запрос пользователя или ответ AI
    """
    MESSAGE_TYPE_USER = 'user'
    MESSAGE_TYPE_ASSISTANT = 'assistant'
    MESSAGE_TYPE_CHOICES = [
        (MESSAGE_TYPE_USER, 'Пользователь'),
        (MESSAGE_TYPE_ASSISTANT, 'Ассистент'),
    ]
    
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    session = models.ForeignKey(ChatSession, on_delete=models.CASCADE, related_name='messages')
    message_type = models.CharField(max_length=20, choices=MESSAGE_TYPE_CHOICES)
    content = models.TextField()
    
    # Временные метки
    created_at = models.DateTimeField(auto_now_add=True)
    request_started_at = models.DateTimeField(null=True, blank=True, help_text='Время начала запроса (для ответов AI)')
    response_received_at = models.DateTimeField(null=True, blank=True, help_text='Время получения ответа')
    processing_time_ms = models.IntegerField(null=True, blank=True, help_text='Время обработки в миллисекундах')
    
    # Метаданные
    metadata = models.JSONField(default=dict, blank=True, help_text='Дополнительные данные (модель, настройки и т.д.)')
    
    class Meta:
        ordering = ['created_at']
        indexes = [
            models.Index(fields=['session', 'created_at']),
        ]
    
    def __str__(self):
        return f"{self.get_message_type_display()} - {self.content[:50]}..."
    
    def calculate_processing_time(self):
        """Вычисляет время обработки на основе временных меток"""
        if self.request_started_at and self.response_received_at:
            delta = self.response_received_at - self.request_started_at
            return int(delta.total_seconds() * 1000)  # в миллисекундах
        return None


class KnowledgeDocument(models.Model):
    """
    Документ в базе знаний RAG
    
    Может хранить либо файл (Word, PDF и т.д.), либо текстовый контент.
    При наличии файла контент извлекается автоматически при индексации.
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='knowledge_documents')
    title = models.CharField(max_length=500, help_text='Название документа')
    
    # Файл документа (Word, PDF и т.д.)
    file = models.FileField(
        upload_to='rag_documents/',
        blank=True,
        null=True,
        help_text='Файл документа (Word, PDF, TXT и т.д.)'
    )
    file_type = models.CharField(
        max_length=50,
        blank=True,
        null=True,
        help_text='Тип файла (docx, pdf, txt и т.д.)'
    )
    
    # Текстовое содержимое (опционально, может быть извлечено из файла или введено вручную)
    content = models.TextField(
        blank=True,
        null=True,
        help_text='Текстовое содержимое документа (извлекается из файла автоматически или вводится вручную)'
    )
    
    source = models.CharField(max_length=500, blank=True, null=True, help_text='Источник документа (URL, путь к файлу и т.д.)')
    
    # Метаданные
    metadata = models.JSONField(default=dict, blank=True, help_text='Дополнительные метаданные документа')
    
    # Временные метки
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    # Статус индексации
    is_indexed = models.BooleanField(default=False, help_text='Индексирован ли документ (разбит на chunks с embeddings)')
    indexed_at = models.DateTimeField(null=True, blank=True, help_text='Время последней индексации')
    
    class Meta:
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['user', '-created_at']),
            models.Index(fields=['is_indexed']),
        ]
    
    def __str__(self):
        return f"{self.title} ({'индексирован' if self.is_indexed else 'не индексирован'})"
    
    @property
    def chunks_count(self):
        return self.chunks.count()


class KnowledgeChunk(models.Model):
    """
    Chunk (фрагмент) документа с векторным embedding для RAG
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    document = models.ForeignKey(KnowledgeDocument, on_delete=models.CASCADE, related_name='chunks')
    
    # Текст chunk
    content = models.TextField(help_text='Содержимое chunk')
    
    # Позиция в документе
    chunk_index = models.IntegerField(help_text='Индекс chunk в документе (порядковый номер)')
    start_char = models.IntegerField(null=True, blank=True, help_text='Начальная позиция в исходном документе')
    end_char = models.IntegerField(null=True, blank=True, help_text='Конечная позиция в исходном документе')
    
    # Векторное представление (embedding)
    embedding = ArrayField(
        models.FloatField(),
        size=None,
        help_text='Векторное представление текста (embedding) для поиска по схожести'
    )
    embedding_model = models.CharField(
        max_length=100,
        help_text='Модель, использованная для генерации embedding'
    )
    
    # Метаданные
    metadata = models.JSONField(default=dict, blank=True, help_text='Дополнительные метаданные chunk')
    
    # Временные метки
    created_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        ordering = ['document', 'chunk_index']
        indexes = [
            models.Index(fields=['document', 'chunk_index']),
            models.Index(fields=['embedding_model']),
        ]
        # Уникальность: один chunk_index на один документ
        unique_together = [['document', 'chunk_index']]
    
    def __str__(self):
        return f"Chunk {self.chunk_index} из документа '{self.document.title}'"
