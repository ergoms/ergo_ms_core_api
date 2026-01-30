from django.apps import AppConfig


class AiAssistantTpConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'src.core.ai_assistant.tp'
    label = 'ai_assistant_tp'
    verbose_name = 'AI Assistant — Техпроцессы'

    def ready(self):
        import src.core.ai_assistant.tp.models  # noqa
