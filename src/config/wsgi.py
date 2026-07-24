"""
Файл содержит конфигурацию для WSGI-приложения Django.

Он устанавливает переменную окружения DJANGO_SETTINGS_MODULE на 'src.config.patterns.development',
что указывает Django, какие настройки использовать для этого окружения. Затем создает WSGI-приложение
с помощью функции get_wsgi_application из django.core.wsgi.
"""

import os

from django.core.wsgi import get_wsgi_application

from src.config.deploy import get_settings_module

os.environ.setdefault('DJANGO_SETTINGS_MODULE', get_settings_module())

application = get_wsgi_application()

# После полной инициализации apps (не в AppConfig.ready — иначе RuntimeWarning).
from src.core.system.runtime_warmup import warmup_runtime_connections

warmup_runtime_connections()
