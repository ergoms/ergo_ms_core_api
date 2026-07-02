"""
Настройки редактирования ФИО пользователями.
"""

from django.conf import settings

from src.core.cms.adp.services.permissions import PermissionService


class ProfileSettingsService:
    RESTRICTED_FIELDS = frozenset({'email', 'first_name', 'last_name', 'middle_name'})
    FIO_FIELDS = frozenset({'first_name', 'last_name', 'middle_name'})

    SELF_EDIT_DISABLED_MESSAGE = (
        'Изменение email и ФИО доступно только администратору. '
        'Отправьте заявку на изменение данных.'
    )

    @staticmethod
    def is_self_fio_edit_enabled() -> bool:
        return bool(getattr(settings, 'USER_PROFILE_SELF_EDIT_ENABLED', True))

    @staticmethod
    def can_user_edit_fio(user) -> bool:
        if ProfileSettingsService.is_self_fio_edit_enabled():
            return True
        if user is None or not getattr(user, 'is_authenticated', False):
            return False
        return PermissionService.can_manage_users_as_global_admin(user)

    @staticmethod
    def get_public_settings() -> dict:
        return {
            'profile_self_edit_enabled': ProfileSettingsService.is_self_fio_edit_enabled(),
        }

    @staticmethod
    def get_self_edit_disabled_message() -> str:
        return ProfileSettingsService.SELF_EDIT_DISABLED_MESSAGE

    @staticmethod
    def get_blocked_profile_fields(data, user) -> set[str]:
        if ProfileSettingsService.can_user_edit_fio(user):
            return set()
        if not isinstance(data, dict):
            return set()
        return ProfileSettingsService.RESTRICTED_FIELDS & set(data.keys())
