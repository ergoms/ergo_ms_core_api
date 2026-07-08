"""
Файл конфигурации Django приложения/модуля ADP.

Этот файл содержит класс конфигурации приложения, который определяет основные настройки,
такие как имя приложения и настройки базы данных по умолчанию.

Класс `AdpConfig`:
    Определяет конфигурацию приложения ADP, включая:
    - Тип поля первичного ключа по умолчанию
    - Имя приложения в системе
"""

from django.apps import AppConfig


def create_system_roles_signal_handler(sender, **kwargs):
    """Создает системные роли после применения миграций."""
    from django.db import OperationalError, ProgrammingError

    from src.core.cms.adp.services.permissions import PermissionService

    try:
        PermissionService.ensure_system_roles()
    except (OperationalError, ProgrammingError):
        pass
    except Exception:
        pass


class AdpConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'src.core.cms.adp'
    label = 'cms_adp'

    def ready(self):
        from src.core.cms.adp import signals  # noqa: F401

        signals.connect_user_signals()

        from django.db.models.signals import post_migrate

        post_migrate.connect(
            create_system_roles_signal_handler,
            sender=self,
            dispatch_uid='cms_adp.create_system_roles',
        )
