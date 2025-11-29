from django.db import models
from django.contrib.auth import get_user_model
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

