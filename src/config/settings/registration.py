"""
Настройки режима регистрации пользователей из переменных окружения (.env).

Режимы:
- open       — свободная регистрация (по умолчанию)
- invitation — только по приглашению администратора
- closed     — регистрация отключена
"""

from src.config.env import env

REGISTRATION_MODE = env.str('API_REGISTRATION_MODE', default='open').strip().lower()
REGISTRATION_INVITATION_TTL_DAYS = env.int('API_REGISTRATION_INVITATION_TTL_DAYS', default=7)

VALID_REGISTRATION_MODES = frozenset({'open', 'invitation', 'closed'})
if REGISTRATION_MODE not in VALID_REGISTRATION_MODES:
    REGISTRATION_MODE = 'open'
