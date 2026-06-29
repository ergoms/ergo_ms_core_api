from django.urls import path

from src.core.cms.adp.consumers.presence import PresenceAdminConsumer, PresenceConsumer

websocket_urlpatterns = [
    path('ws/presence/', PresenceConsumer.as_asgi()),
    path('ws/presence/admin/', PresenceAdminConsumer.as_asgi()),
]
