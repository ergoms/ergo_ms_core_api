"""Приветственные письма при массовом импорте пользователей."""

from __future__ import annotations

from typing import Optional, Tuple

from django.conf import settings
from django.contrib.auth.models import User
from django.core.mail import send_mail

from src.core.utils.methods import _check_email_enabled, _normalize_email_for_recipient, format_smtp_error

DEFAULT_WELCOME_SUBJECT = 'Добро пожаловать в ERGO MS'

DEFAULT_WELCOME_BODY = (
    'Здравствуйте, {full_name}!\n\n'
    'Для вас создана учётная запись в системе ERGO MS.\n\n'
    'Логин: {username}\n'
    'E-mail: {email}\n\n'
    'Войти в систему: {login_url}\n\n'
    'Пароль будет сообщён вам администратором отдельно.'
)

WELCOME_PLACEHOLDERS = [
    {'key': 'first_name', 'label': 'Имя'},
    {'key': 'last_name', 'label': 'Фамилия'},
    {'key': 'middle_name', 'label': 'Отчество'},
    {'key': 'full_name', 'label': 'ФИО'},
    {'key': 'username', 'label': 'Логин'},
    {'key': 'email', 'label': 'E-mail'},
    {'key': 'login_url', 'label': 'Ссылка на вход'},
    {'key': 'password', 'label': 'Пароль (только при отправке письма)'},
]

MAX_SUBJECT_LENGTH = 200
MAX_BODY_LENGTH = 5000


class ImportWelcomeEmailError(Exception):
    def __init__(self, message: str):
        self.message = message
        super().__init__(message)


def get_welcome_email_defaults() -> dict:
    return {
        'subject': DEFAULT_WELCOME_SUBJECT,
        'body': DEFAULT_WELCOME_BODY,
        'placeholders': WELCOME_PLACEHOLDERS,
    }


def build_login_url() -> str:
    base_url = getattr(settings, 'FRONTEND_BASE_URL', 'http://localhost:8001').rstrip('/')
    return f'{base_url}/login'


def _build_full_name(user: User) -> str:
    parts = [user.last_name, user.first_name]
    middle_name = getattr(user, 'middle_name', '') or ''
    if middle_name:
        parts.append(middle_name)
    return ' '.join(part for part in parts if part).strip() or user.username


def normalize_welcome_templates(
    subject: Optional[str],
    body: Optional[str],
) -> tuple[str, str]:
    normalized_subject = (subject or '').strip() or DEFAULT_WELCOME_SUBJECT
    normalized_body = (body or '').strip() or DEFAULT_WELCOME_BODY

    if len(normalized_subject) > MAX_SUBJECT_LENGTH:
        raise ImportWelcomeEmailError(
            f'Тема письма не должна превышать {MAX_SUBJECT_LENGTH} символов.',
        )
    if len(normalized_body) > MAX_BODY_LENGTH:
        raise ImportWelcomeEmailError(
            f'Текст письма не должен превышать {MAX_BODY_LENGTH} символов.',
        )
    return normalized_subject, normalized_body


def render_welcome_email(
    user: User,
    *,
    subject_template: str,
    body_template: str,
    password: str = '',
) -> tuple[str, str]:
    context = {
        'first_name': user.first_name or '',
        'last_name': user.last_name or '',
        'middle_name': getattr(user, 'middle_name', '') or '',
        'full_name': _build_full_name(user),
        'username': user.username or '',
        'email': user.email or '',
        'login_url': build_login_url(),
        'password': password or '',
    }

    def _replace(template: str) -> str:
        result = template
        for key, value in context.items():
            result = result.replace(f'{{{key}}}', value)
        return result

    return _replace(subject_template), _replace(body_template)


def send_import_welcome_email(
    recipient_email: str,
    subject: str,
    body: str,
) -> Tuple[bool, Optional[str]]:
    disabled = _check_email_enabled()
    if disabled is not None:
        return disabled

    try:
        default_from_email = getattr(settings, 'DEFAULT_FROM_EMAIL', None)
        if not default_from_email:
            error_msg = 'SMTP не настроен: отсутствует DEFAULT_FROM_EMAIL'
            return False, error_msg

        normalized_email = _normalize_email_for_recipient(recipient_email)
        if not normalized_email:
            return False, 'Недопустимый адрес получателя'

        send_mail(
            subject,
            body,
            default_from_email,
            [normalized_email],
            fail_silently=False,
        )
        return True, None
    except Exception as exc:
        error_msg = format_smtp_error(exc)
        return False, error_msg


def parse_send_welcome_emails_flag(raw_value) -> bool:
    if raw_value is None:
        return False
    return str(raw_value).lower() in ('true', '1', 'yes')
