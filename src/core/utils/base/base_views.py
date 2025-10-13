"""
Базовые классы представлений API.
"""

from rest_framework.views import APIView
from rest_framework_simplejwt.authentication import JWTAuthentication
from rest_framework.throttling import AnonRateThrottle, UserRateThrottle
from rest_framework.permissions import IsAuthenticated


class BaseAPIView(APIView):
    """
    Базовый класс для всех API представлений.
    
    Включает:
    - JWT аутентификацию
    - Ограничение частоты запросов
    """
    authentication_classes = [JWTAuthentication]
    throttle_classes = [AnonRateThrottle, UserRateThrottle]

class BaseAPIViewAuthMixin(BaseAPIView):
    """
    Базовый класс для всех API представлений с аутентификацией.
    """
    permission_classes = [IsAuthenticated]