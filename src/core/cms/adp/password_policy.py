"""
Централизованная политика паролей ADP.
Читает настройки из Django settings (загружаются из .env через config/settings/password.py).
"""

import re

from django.conf import settings
from django.core.exceptions import ValidationError as DjangoValidationError
from rest_framework.serializers import ValidationError


SPECIAL_CHAR_PATTERN = re.compile(r'[^A-Za-z0-9]')


def _policy():
    return getattr(settings, 'PASSWORD_POLICY', {})


def _min_length():
    return int(_policy().get('min_length', 8))


def _max_length():
    return int(_policy().get('max_length', 128))


def _require_lowercase():
    return bool(_policy().get('require_lowercase', True))


def _require_uppercase():
    return bool(_policy().get('require_uppercase', False))


def _require_digit():
    return bool(_policy().get('require_digit', True))


def _require_special():
    return bool(_policy().get('require_special', False))


def _collect_password_errors(password: str) -> list[str]:
    errors = []

    if len(password) < _min_length():
        errors.append(f'Пароль должен содержать минимум {_min_length()} символов.')

    max_length = _max_length()
    if max_length > 0 and len(password) > max_length:
        errors.append(f'Пароль должен содержать не более {max_length} символов.')

    if _require_lowercase() and not any(c.islower() for c in password):
        errors.append('Пароль должен содержать хотя бы одну букву в нижнем регистре.')

    if _require_uppercase() and not any(c.isupper() for c in password):
        errors.append('Пароль должен содержать хотя бы одну букву в верхнем регистре.')

    if _require_digit() and not any(c.isdigit() for c in password):
        errors.append('Пароль должен содержать хотя бы одну цифру.')

    if _require_special() and not SPECIAL_CHAR_PATTERN.search(password):
        errors.append('Пароль должен содержать хотя бы один специальный символ.')

    return errors


def get_password_requirement_hints() -> list[str]:
    hints = [f'Минимум {_min_length()} символов']

    max_length = _max_length()
    if max_length > 0:
        hints.append(f'Не более {max_length} символов')

    if _require_lowercase():
        hints.append('Хотя бы одна строчная буква')
    if _require_uppercase():
        hints.append('Хотя бы одна заглавная буква')
    if _require_digit():
        hints.append('Хотя бы одна цифра')
    if _require_special():
        hints.append('Хотя бы один специальный символ')

    return hints


def validate_password_value(password: str, user=None) -> None:
    errors = _collect_password_errors(password)
    if errors:
        raise DjangoValidationError(errors)


def validate_new_password_pair(attrs):
    """Общая валидация пары new_password / confirm_password."""
    new_password = attrs.get('new_password', '')
    confirm_password = attrs.get('confirm_password', '')

    if new_password != confirm_password:
        raise ValidationError('Новый пароль и подтверждение не совпадают.')

    try:
        validate_password_value(new_password)
    except DjangoValidationError as exc:
        raise ValidationError(list(exc.messages))

    return attrs


class MaxLengthValidator:
    def __init__(self, max_length=128):
        self.max_length = max_length

    def validate(self, password, user=None):
        if self.max_length > 0 and len(password) > self.max_length:
            raise DjangoValidationError(
                f'Пароль должен содержать не более {self.max_length} символов.',
                code='password_too_long',
            )

    def get_help_text(self):
        return f'Пароль не должен содержать более {self.max_length} символов.'


class PasswordPolicyValidator:
    def validate(self, password, user=None):
        validate_password_value(password, user=user)

    def get_help_text(self):
        return '; '.join(get_password_requirement_hints())
