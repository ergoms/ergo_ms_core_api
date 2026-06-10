"""Форматирование ошибок SMTP для пользовательских сообщений."""


def format_smtp_error(exc: Exception) -> str:
    error_str = str(exc)
    error_type = type(exc).__name__

    if 'SMTPAuthenticationError' in error_type or '535' in error_str:
        return (
            'Ошибка аутентификации SMTP. Проверьте:\n'
            '1. Правильность EMAIL_HOST_USER и EMAIL_HOST_PASSWORD в .env\n'
            '2. Для Gmail/Mail.ru может потребоваться пароль приложения вместо обычного пароля\n'
            '3. Убедитесь, что EMAIL_USE_TLS / EMAIL_USE_SSL настроены правильно'
        )
    if 'SMTPConnectError' in error_type or 'Connection refused' in error_str:
        return (
            'Не удалось подключиться к SMTP серверу. Проверьте:\n'
            '1. Правильность EMAIL_HOST и EMAIL_PORT в .env\n'
            '2. Доступность SMTP сервера'
        )
    return f'Ошибка отправки email: {error_str}'
