from django.apps import AppConfig


class NotificationsConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'src.core.notifications'
    label = 'core_notifications'
    verbose_name = 'Уведомления'

    def ready(self):
        from . import integrations  # noqa: F401
