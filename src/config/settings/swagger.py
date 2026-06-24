"""
Настройки доступа к документации API (Swagger UI / ReDoc) из переменных окружения (.env).
"""

from src.config.env import env

_deploy_type = env.str('API_DEPLOY_TYPE', default='production').strip().lower()
_default_swagger_enabled = _deploy_type != 'production'

SWAGGER_ENABLED = env.bool('API_SWAGGER_ENABLED', default=_default_swagger_enabled)
