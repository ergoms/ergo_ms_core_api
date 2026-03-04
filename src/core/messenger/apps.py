from django.apps import AppConfig


class MessengerConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'src.core.messenger'
    label = 'core_messenger'
    verbose_name = 'Мессенджер'
