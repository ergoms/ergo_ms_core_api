"""
Настройки редактирования профиля пользователями из переменных окружения (.env).

API_USER_PROFILE_SELF_EDIT_ENABLED:
- true  — пользователи могут менять email и ФИО в настройках профиля (по умолчанию)
- false — email и ФИО меняют только глобальные администраторы; пользователи отправляют заявки
"""

from src.config.env import env

USER_PROFILE_SELF_EDIT_ENABLED = env.bool('API_USER_PROFILE_SELF_EDIT_ENABLED', default=True)
