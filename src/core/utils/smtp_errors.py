"""Форматирование ошибок SMTP для пользовательских сообщений."""

USER_EMAIL_DELIVERY_FAILED = (
    'Не удалось отправить письмо. Обратитесь к администратору системы.'
)

_EMAIL_INTERNAL_MARKERS = (
    'EMAIL_ENABLED',
    'EMAIL_HOST',
    'EMAIL_PORT',
    'EMAIL_USE_TLS',
    'EMAIL_USE_SSL',
    'EMAIL_HOST_USER',
    'EMAIL_HOST_PASSWORD',
    'DEFAULT_FROM_EMAIL',
    'EmailSettings',
    '.env',
    'smtp_host',
    'smtp_port',
)


def sanitize_email_delivery_message(message: str | None) -> str | None:
    """Убирает из текста имена env-переменных и прочие внутренние детали конфигурации."""
    if not message:
        return None
    if any(marker in message for marker in _EMAIL_INTERNAL_MARKERS):
        return USER_EMAIL_DELIVERY_FAILED
    return message


def _is_mailbox_unavailable(error_lower: str) -> bool:
    mailbox_markers = ('invalid mailbox', 'does not exist', 'mailbox not found')
    if any(marker in error_lower for marker in mailbox_markers):
        return True
    if 'mailbox' in error_lower and ('unavailable' in error_lower or 'disabled' in error_lower):
        return True
    return False


def _is_recipient_rejected(error_lower: str) -> bool:
    return 'recipient rejected' in error_lower or 'user unknown' in error_lower


def format_smtp_error(exc: Exception) -> str:
    error_str = str(exc)
    error_type = type(exc).__name__
    error_lower = error_str.lower()

    if 'SMTPAuthenticationError' in error_type or '535' in error_str:
        return USER_EMAIL_DELIVERY_FAILED

    if 'SMTPConnectError' in error_type or 'connection refused' in error_lower:
        return 'Не удалось связаться с почтовым сервером. Попробуйте позже.'

    if 'timeout' in error_lower or 'timed out' in error_lower:
        return 'Не удалось связаться с почтовым сервером. Попробуйте позже.'

    is_data_error = 'SMTPDataError' in error_type
    is_550 = '550' in error_str

    if is_data_error or is_550:
        if _is_mailbox_unavailable(error_lower):
            return (
                'Почтовый ящик получателя недоступен или отключён. '
                'Проверьте email пользователя.'
            )
        if _is_recipient_rejected(error_lower):
            return (
                'Почтовый сервер не принимает письма на этот адрес. '
                'Проверьте email пользователя.'
            )
        if is_550:
            return 'Почтовый сервер отклонил доставку на указанный адрес.'

    if 'SMTPException' in error_type:
        return 'Не удалось связаться с почтовым сервером. Попробуйте позже.'

    return USER_EMAIL_DELIVERY_FAILED
