from django.apps import AppConfig


class NotificationsConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'src.core.notifications'
    label = 'core_notifications'
    verbose_name = 'Уведомления'

    def ready(self):
        from src.core.utils.django_cli import is_lean_schema_cli

        if is_lean_schema_cli():
            return

        from . import integrations  # noqa: F401
