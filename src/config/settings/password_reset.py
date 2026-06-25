"""
Настройки восстановления пароля из переменных окружения (.env).

API_PASSWORD_RESET_ENABLED:
- true  — пользователи могут восстанавливать пароль через форму «Забыл пароль» (по умолчанию)
- false — самостоятельное восстановление пароля отключено
"""

from src.config.env import env

PASSWORD_RESET_ENABLED = env.bool('API_PASSWORD_RESET_ENABLED', default=True)
