from django.apps import AppConfig


class AuditConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'src.core.audit'
    label = 'core_audit'
    verbose_name = 'Журнал действий'

    def ready(self):
        from src.core.utils.django_cli import is_lean_schema_cli

        if is_lean_schema_cli():
            return

        from . import integrations  # noqa: F401
