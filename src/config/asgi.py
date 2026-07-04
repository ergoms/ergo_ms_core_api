"""
Файл содержит конфигурацию для ASGI-приложения Django.

Он устанавливает переменную окружения DJANGO_SETTINGS_MODULE на 'src.config.patterns.development',
что указывает Django, какие настройки использовать для этого окружения. Затем создает ASGI-приложение
с помощью функции get_asgi_application из django.core.asgi.
"""

import os

from django.core.asgi import get_asgi_application

from src.config.deploy import get_settings_module

os.environ.setdefault('DJANGO_SETTINGS_MODULE', get_settings_module())

django_asgi_app = get_asgi_application()

from channels.auth import AuthMiddlewareStack
from channels.routing import ProtocolTypeRouter, URLRouter

from src.core.messenger.routing import websocket_urlpatterns as messenger_ws
from src.core.notifications.routing import websocket_urlpatterns as notifications_ws
from src.core.cms.adp.routing import websocket_urlpatterns as adp_ws

application = ProtocolTypeRouter({
    "http": django_asgi_app,
    "websocket": AuthMiddlewareStack(
        URLRouter(messenger_ws + notifications_ws + adp_ws)
    ),
})
