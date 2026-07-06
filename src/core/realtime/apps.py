from django.apps import AppConfig


class RealtimeConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'src.core.realtime'
    label = 'core_realtime'
    verbose_name = 'Realtime'

    def ready(self):
        from src.core.realtime.core_topics import register_core_realtime_topics
        register_core_realtime_topics()
