from django.contrib.auth.models import User
from django.db.models.signals import post_save
from django.dispatch import receiver
from django.db import OperationalError, ProgrammingError
import logging

from src.core.cms.adp.models import UserRole
from src.core.cms.adp.services.permissions import PermissionService

logger = logging.getLogger(__name__)


@receiver(post_save, sender=User)
def assign_default_role_on_create(sender, instance, created, **kwargs):
    """Назначает роль новым пользователям: «Администратор» суперюзерам, «Пользователь» остальным."""
    if not created:
        return
    
    try:
        # Проверяем, существует ли уже роль у пользователя
        if UserRole.objects.filter(user=instance).exists():
            return

        if getattr(instance, 'is_superuser', False):
            admin_role = PermissionService._get_or_create_admin_role()
            PermissionService.assign_role_to_user(instance, admin_role)
            return
        
        PermissionService.assign_default_role(instance)
    except (OperationalError, ProgrammingError) as e:
        # Таблица Role может не существовать, если миграции не применены
        logger.warning(
            f"Не удалось назначить роль пользователю {instance.username}: {e}. "
            "Возможно, миграции не применены. Примените миграции командой: api makemigrations && api migrate"
        )
    except Exception as e:
        # Логируем другие ошибки, но не прерываем создание пользователя
        logger.error(
            f"Ошибка при назначении роли пользователю {instance.username}: {e}",
            exc_info=True
        )

