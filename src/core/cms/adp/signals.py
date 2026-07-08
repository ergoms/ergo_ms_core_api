from django.contrib.auth import get_user_model
from django.db.models.signals import post_save
from django.db import OperationalError, ProgrammingError
import logging

from src.core.cms.adp.models import UserRole
from src.core.cms.adp.services.permissions import PermissionService

logger = logging.getLogger(__name__)


def _ensure_global_admin_role(user) -> None:
    """Django superuser и ADP-роль «Администратор» — единая сущность."""
    admin_role = PermissionService._get_or_create_admin_role()
    has_active_admin = UserRole.objects.filter(
        user=user,
        role=admin_role,
        is_active=True,
    ).exists()
    if not has_active_admin:
        PermissionService.assign_role_to_user(user, admin_role)


def sync_user_role_on_save(sender, instance, created, **kwargs):
    """
    Синхронизирует ADP-роль с флагами Django admin:
    - is_superuser=True → роль «Администратор»;
    - новым обычным пользователям — «Пользователь».
    """
    try:
        if getattr(instance, 'is_superuser', False):
            _ensure_global_admin_role(instance)
            return

        if not created:
            return

        if UserRole.objects.filter(user=instance).exists():
            return

        PermissionService.assign_default_role(instance)
    except (OperationalError, ProgrammingError) as e:
        logger.warning(
            f"Не удалось назначить роль пользователю {instance.username}: {e}. "
            "Возможно, миграции не применены. Примените миграции командой: ergoms db-migrate"
        )
    except Exception as e:
        logger.error(
            f"Ошибка при назначении роли пользователю {instance.username}: {e}",
            exc_info=True
        )


def connect_user_signals() -> None:
    """Подключает сигналы к текущей модели пользователя (ErgoUser)."""
    user_model = get_user_model()
    post_save.connect(
        sync_user_role_on_save,
        sender=user_model,
        dispatch_uid='cms_adp.sync_user_role_on_save',
    )
