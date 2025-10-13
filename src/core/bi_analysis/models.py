from django.db import models

# Создавайте свои модели здесь
class ReportConfig(models.Model): 
    SOURCE_CHOICES = [ # Список возможных источников данных для отчёта
        ('postgres', 'PostgreSQL'),
        ('mssql', 'MS SQL Server'),
        ('clickhouse', 'ClickHouse'),
    ]

    name = models.CharField(max_length=255)
    description = models.TextField(blank=True)
    source_type = models.CharField(max_length=16, choices=SOURCE_CHOICES) # Источник БД
    query = models.TextField()
    is_active = models.BooleanField(default=True) # Флаг, можно ли сейчас запускать этот отчёт

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self): # Отображение отчёта в админке и логах
        return f"[{self.source_type}] {self.name}"


class ReportExecutionLog(models.Model):
    STATUS_CHOICES = [ # Перечисление возможных статусов выполнения
        ('success', 'Success'),
        ('error', 'Error'),
    ]

    report = models.ForeignKey(ReportConfig, on_delete=models.CASCADE, related_name='executions') # Связь с конфигурацией отчёта
    executed_at = models.DateTimeField(auto_now_add=True) # Дата и время запуска
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='success') # Статус выполнения
    duration_ms = models.IntegerField() # Продолжительность
    error_message = models.TextField(blank=True, null=True)

    def __str__(self): # Сообщение о статусе выполнения запроса
        return f"{self.report.name} @ {self.executed_at} ({self.status})"


class ReportResult(models.Model):
    report = models.ForeignKey(ReportConfig, on_delete=models.CASCADE, related_name='results') 
    execution = models.ForeignKey(ReportExecutionLog, on_delete=models.SET_NULL, null=True, blank=True)
    # Связь с отчётом и логом выполнения. Если лог удалится, execution может стать NULL, но сам результат сохранится.
    
    result_data = models.JSONField()
    row_count = models.IntegerField()
    saved_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"Result for {self.report.name} ({self.row_count} rows)"