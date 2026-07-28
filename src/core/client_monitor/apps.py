from django.apps import AppConfig


class ClientMonitorConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'src.core.client_monitor'
    label = 'core_client_monitor'
    verbose_name = 'Мониторинг клиентов'
