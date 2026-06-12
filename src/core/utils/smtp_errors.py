"""Форматирование ошибок SMTP для пользовательских сообщений."""


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
        return (
            'Ошибка аутентификации SMTP. Проверьте:\n'
            '1. Правильность EMAIL_HOST_USER и EMAIL_HOST_PASSWORD в .env\n'
            '2. Для Gmail/Mail.ru может потребоваться пароль приложения вместо обычного пароля\n'
            '3. Убедитесь, что EMAIL_USE_TLS / EMAIL_USE_SSL настроены правильно'
        )

    if 'SMTPConnectError' in error_type or 'connection refused' in error_lower:
        return (
            'Не удалось подключиться к SMTP серверу. Проверьте:\n'
            '1. Правильность EMAIL_HOST и EMAIL_PORT в .env\n'
            '2. Доступность SMTP сервера'
        )

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

    return 'Не удалось отправить email. Обратитесь к администратору системы.'
