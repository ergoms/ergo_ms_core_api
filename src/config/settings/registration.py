"""
Настройки режима регистрации пользователей из переменных окружения (.env).

Режимы:
- open       — свободная регистрация (по умолчанию)
- invitation — только по приглашению администратора
- closed     — регистрация отключена

REGISTRATION_CHECK_EMAIL_EXISTS — глобальная проверка уникальности email
(регистрация, обновление профиля, массовый импорт).
"""

from src.config.env import env

REGISTRATION_MODE = env.str('API_REGISTRATION_MODE', default='open').strip().lower()
REGISTRATION_INVITATION_TTL_DAYS = env.int('API_REGISTRATION_INVITATION_TTL_DAYS', default=7)
REGISTRATION_CHECK_EMAIL_EXISTS = env.bool('API_REGISTRATION_CHECK_EMAIL_EXISTS', default=False)
VALID_REGISTRATION_MODES = frozenset({'open', 'invitation', 'closed'})
if REGISTRATION_MODE not in VALID_REGISTRATION_MODES:
    REGISTRATION_MODE = 'open'
