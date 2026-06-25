"""
Сервис настроек восстановления пароля пользователями.
"""

from django.conf import settings


class PasswordResetService:
    PURPOSE_PASSWORD_RESET = 'password_reset'

    DISABLED_MESSAGE = (
        'Восстановление пароля отключено администратором. '
        'Обратитесь к администратору системы.'
    )

    @staticmethod
    def is_enabled() -> bool:
        return bool(getattr(settings, 'PASSWORD_RESET_ENABLED', True))

    @staticmethod
    def get_public_settings() -> dict:
        enabled = PasswordResetService.is_enabled()
        return {
            'password_reset_enabled': enabled,
        }

    @staticmethod
    def get_disabled_message() -> str:
        return PasswordResetService.DISABLED_MESSAGE

    @staticmethod
    def is_password_reset_purpose(purpose: str) -> bool:
        return (purpose or '').strip().lower() == PasswordResetService.PURPOSE_PASSWORD_RESET
