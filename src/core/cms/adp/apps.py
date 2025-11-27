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
    from src.core.cms.adp.services.permissions import PermissionService
    from django.db import OperationalError, ProgrammingError
    
    try:
        PermissionService.ensure_system_roles()
    except (OperationalError, ProgrammingError):
        # Таблицы еще не созданы - это нормально
        pass
    except Exception:
        # Игнорируем любые другие ошибки
        pass


class AdpConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'src.core.cms.adp'
    label = 'cms_adp'

    def ready(self):
        # Регистрация сигналов приложения ADP
        from src.core.cms.adp import signals  # noqa: F401
        
        # Регистрируем обработчик для создания системных ролей после миграций
        from django.db.models.signals import post_migrate
        
        post_migrate.connect(
            create_system_roles_signal_handler,
            sender=self,
            dispatch_uid='cms_adp.create_system_roles'
        )
