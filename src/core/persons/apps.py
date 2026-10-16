from django.apps import AppConfig


class PersonsConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'src.core.persons'
    label = 'core_persons'
    verbose_name = 'Карточки людей'

    def ready(self):
        from src.core.utils.django_cli import is_lean_schema_cli

        if is_lean_schema_cli():
            return

        from . import integrations  # noqa: F401
