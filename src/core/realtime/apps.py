from django.apps import AppConfig


class RealtimeConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'src.core.realtime'
    label = 'core_realtime'
    verbose_name = 'Realtime'

    def ready(self):
        from src.core.utils.django_cli import is_lean_schema_cli

        if is_lean_schema_cli():
            return

        from src.core.realtime.core_topics import register_core_realtime_topics
        register_core_realtime_topics()
