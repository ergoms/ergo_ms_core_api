from django.apps import AppConfig


class LcpConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'src.core.lcp'
    label = 'lcp'
    verbose_name = 'Low-Code Platform'


