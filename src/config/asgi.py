"""
Файл содержит конфигурацию для ASGI-приложения Django.

Он устанавливает переменную окружения DJANGO_SETTINGS_MODULE на 'src.config.patterns.development',
что указывает Django, какие настройки использовать для этого окружения. Затем создает ASGI-приложение
с помощью функции get_asgi_application из django.core.asgi.
"""

import os

from django.core.asgi import get_asgi_application

from src.core.utils.auto_api.auto_config import get_env_deploy_type

deploy_type = get_env_deploy_type()
os.environ.setdefault('DJANGO_SETTINGS_MODULE', deploy_type)

application = get_asgi_application()