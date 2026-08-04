"""
Базовые классы представлений API.
"""

from rest_framework.views import APIView
from rest_framework.throttling import AnonRateThrottle, UserRateThrottle
from rest_framework.permissions import AllowAny, IsAuthenticated

from src.core.settings.permissions import IsGlobalAdmin


class BaseAPIView(APIView):
    """
    Базовый класс для публичных API представлений (login, register, reset).

    Включает:
    - Ограничение частоты запросов
    - Публичный доступ (AllowAny)

    Аутентификация не переопределяется — действует DEFAULT_AUTHENTICATION_CLASSES
    (DeviceBoundJWTAuthentication), поэтому Bearer-токен с отозванной сессией
    устройства отклоняется и на анонимных по permission_classes представлениях.
    """
    throttle_classes = [AnonRateThrottle, UserRateThrottle]
    permission_classes = [AllowAny]

class BaseAPIViewAuthMixin(BaseAPIView):
    """
    Базовый класс для всех API представлений с аутентификацией.
    """
    permission_classes = [IsAuthenticated]


class BaseAPIViewGlobalAdminMixin(BaseAPIViewAuthMixin):
    """API представления, доступные только глобальному администратору."""
    permission_classes = [IsAuthenticated, IsGlobalAdmin]