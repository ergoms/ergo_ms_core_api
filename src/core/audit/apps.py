from django.apps import AppConfig


class AuditConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'src.core.audit'
    label = 'core_audit'
    verbose_name = 'Журнал действий'

    def ready(self):
        from . import integrations  # noqa: F401
