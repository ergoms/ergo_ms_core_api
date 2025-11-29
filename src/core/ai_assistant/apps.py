from django.apps import AppConfig


class AiAssistantConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'src.core.ai_assistant'
    label = 'ai_assistant'
    
    def ready(self):
        """Импортируем модели при запуске приложения"""
        import src.core.ai_assistant.models  # noqa


