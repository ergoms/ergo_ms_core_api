"""
Настройки Django REST Framework из переменных окружения (.env).
"""

from src.config.env import env

_deploy_type = env.str('API_DEPLOY_TYPE', default='production').strip().lower()
_default_browsable_enabled = _deploy_type != 'production'

DRF_BROWSABLE_ENABLED = env.bool('API_DRF_BROWSABLE_ENABLED', default=_default_browsable_enabled)
