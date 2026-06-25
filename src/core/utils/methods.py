"""
Файл с вспомогательными методами.

Этот файл содержит различные вспомогательные методы, которые используются в других частях модуля и приложения.
"""

import logging
import re
import secrets
import string
from typing import Dict, Tuple, Optional

from django.contrib.auth import password_validation
from django.core.exceptions import ValidationError as DjangoValidationError
from django.core.mail import send_mail
from django.conf import settings

from src.core.utils.smtp_errors import format_smtp_error

logger = logging.getLogger(__name__)


def _normalize_email_for_recipient(email: str) -> str:
    """Удаляет из адреса символы, способные вызвать подмену заголовков (CRLF, управляющие)."""
    if not email or not isinstance(email, str):
        return ""
    first_line = email.strip().splitlines()[0].strip()
    return re.sub(r"[\r\n\x00-\x1f\x7f]", "", first_line)

def parse_errors_to_dict(error_dict: Dict[str, list]) -> Dict[str, str]:
    """
    Преобразует словарь ошибок в строковый формат.

    Аргументы:
        error_dict (Dict[str, list]): Словарь, где ключи - это поля, а значения - списки ошибок.

    Возвращает:
        Dict[str, str]: Словарь, где ключи - это поля, а значения - строки, содержащие ошибки, разделенные запятыми.
    """
    parsed_errors = {}

    for field, details in error_dict.items():
        parsed_errors[field] = ", ".join(str(detail) for detail in details)
        
    return parsed_errors

def send_confirmation_email(email: str, code: str) -> Tuple[bool, Optional[str]]:
    """
    Отправляет email с кодом подтверждения.

    Аргументы:
        email (str): Email адрес получателя.
        code (str): Код подтверждения.

    Возвращает:
        tuple[bool, str]: (успех, сообщение об ошибке или None)
    """
    import logging
    logger = logging.getLogger(__name__)
    
    try:
        default_from_email = getattr(settings, 'DEFAULT_FROM_EMAIL', None)
        
        if not default_from_email:
            error_msg = "SMTP не настроен: отсутствует DEFAULT_FROM_EMAIL"
            logger.error(error_msg)
            return False, error_msg

        subject = "Код подтверждения ERGO MS"
        message = f"Ваш код подтверждения: {code}"
        from_email = default_from_email
        normalized_email = _normalize_email_for_recipient(email)
        if not normalized_email:
            error_msg = "Недопустимый адрес получателя"
            logger.warning(error_msg)
            return False, error_msg
        recipient_list = [normalized_email]

        send_mail(subject,
                  message, 
                  from_email, 
                  recipient_list, 
                  fail_silently=False)
        
        return True, None
        
    except Exception as e:
        error_msg = format_smtp_error(e)
        logger.error('SMTP Error (%s): %s', type(e).__name__, error_msg, exc_info=True)
        return False, error_msg


def generate_secure_random_password(length: int = 16, max_attempts: int = 50) -> str:
    """Генерирует пароль, проходящий AUTH_PASSWORD_VALIDATORS и правила ADP."""
    min_length = getattr(settings, 'PASSWORD_MIN_LENGTH', 8)
    if length < min_length:
        length = min_length

    alphabet = string.ascii_letters + string.digits + '!@#$%&*-_=+'
    rng = secrets.SystemRandom()

    for _ in range(max_attempts):
        chars = []
        if getattr(settings, 'PASSWORD_REQUIRE_LOWERCASE', True):
            chars.append(rng.choice(string.ascii_lowercase))
        if getattr(settings, 'PASSWORD_REQUIRE_UPPERCASE', False):
            chars.append(rng.choice(string.ascii_uppercase))
        if getattr(settings, 'PASSWORD_REQUIRE_DIGIT', True):
            chars.append(rng.choice(string.digits))
        if getattr(settings, 'PASSWORD_REQUIRE_SPECIAL', False):
            chars.append(rng.choice('!@#$%&*-_=+'))
        if not chars:
            chars.append(rng.choice(string.ascii_lowercase))
        chars.extend(rng.choice(alphabet) for _ in range(length - len(chars)))
        rng.shuffle(chars)
        candidate = ''.join(chars)
        try:
            password_validation.validate_password(candidate)
            from src.core.cms.adp.password_policy import validate_new_password_pair

            validate_new_password_pair({
                'new_password': candidate,
                'confirm_password': candidate,
            })
            return candidate
        except Exception:
            continue

    raise RuntimeError('Не удалось сгенерировать допустимый пароль')


def send_admin_password_reset_notification(email: str) -> Tuple[bool, Optional[str]]:
    """Уведомление о сбросе пароля администратором (без пароля и без кода)."""
    try:
        default_from_email = getattr(settings, 'DEFAULT_FROM_EMAIL', None)
        if not default_from_email:
            error_msg = 'SMTP не настроен: отсутствует DEFAULT_FROM_EMAIL'
            logger.warning(error_msg)
            return False, error_msg

        normalized_email = _normalize_email_for_recipient(email)
        if not normalized_email:
            error_msg = 'Недопустимый адрес получателя'
            logger.warning(error_msg)
            return False, error_msg

        from src.core.cms.adp.services.password_reset import PasswordResetService

        subject = 'Сброс пароля администратором — ERGO MS'
        if PasswordResetService.is_enabled():
            recovery_hint = (
                'Для восстановления доступа воспользуйтесь формой «Забыл пароль» '
                'на странице входа в систему.'
            )
        else:
            recovery_hint = (
                'Для восстановления доступа обратитесь к администратору системы.'
            )
        message = (
            'Администратор системы сбросил пароль вашей учётной записи.\n\n'
            'Текущий пароль никому не известен — ни вам, ни администраторам — в целях безопасности.\n\n'
            f'{recovery_hint}'
        )

        send_mail(
            subject,
            message,
            default_from_email,
            [normalized_email],
            fail_silently=False,
        )
        return True, None
    except Exception as e:
        error_msg = format_smtp_error(e)
        logger.warning(
            'Не удалось отправить уведомление о сбросе пароля (%s): %s',
            type(e).__name__,
            error_msg,
        )
        return False, error_msg


def send_registration_invitation_email(
    email: str,
    invite_url: str,
    ttl_days: int,
) -> Tuple[bool, Optional[str]]:
    """Отправляет email с ссылкой-приглашением на регистрацию."""
    try:
        default_from_email = getattr(settings, 'DEFAULT_FROM_EMAIL', None)
        if not default_from_email:
            error_msg = 'SMTP не настроен: отсутствует DEFAULT_FROM_EMAIL'
            logger.error(error_msg)
            return False, error_msg

        normalized_email = _normalize_email_for_recipient(email)
        if not normalized_email:
            error_msg = 'Недопустимый адрес получателя'
            logger.warning(error_msg)
            return False, error_msg

        subject = 'Приглашение в ERGOMS'
        message = (
            f'Вас пригласили зарегистрироваться в системе ERGOMS.\n\n'
            f'Перейдите по ссылке для создания учётной записи:\n{invite_url}\n\n'
            f'Ссылка действительна {ttl_days} дн.'
        )

        send_mail(
            subject,
            message,
            default_from_email,
            [normalized_email],
            fail_silently=False,
        )
        return True, None
    except Exception as e:
        error_msg = format_smtp_error(e)
        logger.error('SMTP Error (%s): %s', type(e).__name__, error_msg, exc_info=True)
        return False, error_msg


def convert_snake_to_camel(snake_text: str) -> str:
    """
    Преобразует строку в формате snake_case в CamelCase.

    Формирует строку в формате CamelCase, разделяя исходную строку по символам подчёркивания,
    преобразуя каждую часть в капитализированный формат и объединяя их.

    Аргументы:
        snake_str (str): Строка в формате snake_case для преобразования.

    Возвращает:
        str: Строка в формате CamelCase.
    """
    # Разделяем строку по символу подчеркивания, капитализируем каждую часть и объединяем их
    return ''.join(word.capitalize() for word in snake_text.split('_'))

def convert_path_to_dot_notation(path) -> str:
    """
    Преобразует путь из формата Path в формат с точками.

    Преобразует строку пути, заменяя разделители путей (слэши) на точки.
    Например: 'src/core' -> 'src.core'

    Аргументы:
        path: Путь для преобразования (str или Path).

    Возвращает:
        str: Путь в формате с точками.
    """
    # Преобразуем в строку, если это объект Path
    path_str = str(path)
    # Заменяем слэши на точки и убираем лишние точки
    return path_str.replace('/', '.').replace('\\', '.').strip('.')