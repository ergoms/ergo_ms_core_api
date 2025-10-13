"""
Конфигурация Django приложения для Ollama Framework
"""

from django.apps import AppConfig


class OllamaFrameworkConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'src.core.ollama_framework'
    verbose_name = 'Ollama Framework'
    
    def ready(self):
        """Инициализация приложения при запуске Django"""
        pass