"""
Настройки Django REST Framework из переменных окружения (.env).
"""

from src.config.env import env
from src.config.deploy import is_development

_default_browsable_enabled = is_development()

DRF_BROWSABLE_ENABLED = env.bool('API_DRF_BROWSABLE_ENABLED', default=_default_browsable_enabled)
