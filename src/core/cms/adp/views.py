from rest_framework.response import Response
from rest_framework import status
from drf_yasg.utils import swagger_auto_schema
from drf_yasg import openapi

import logging

from src.core.cms.adp.models import UserProfile
from src.core.cms.adp.serializers import CMSUserMenuSerializer
from src.core.utils.base.base_views import BaseAPIView, BaseAPIViewAuthMixin
from src.core.cms.adp.services.session_devices import (
    ensure_legacy_device,
    touch_device_activity,
)
from src.core.cms.adp.auth_cookies import clear_auth_cookies

logger = logging.getLogger(__name__)


def _audit_event(action, *, request=None, actor=None, severity='info', meta=None, entity=None):
    """Безопасная запись действия в единый журнал ядра через ModuleBridge."""
    try:
        from src.core.integrations import bridge
        bridge.call(
            'audit.record',
            action=action,
            source_module='core.cms.adp',
            request=request,
            actor=actor,
            severity=severity,
            meta=meta,
            entity=entity,
        )
    except Exception:
        logger.debug('Не удалось записать аудит %s', action, exc_info=True)


class UserMenuView(BaseAPIViewAuthMixin):
    """
    Легковесный endpoint для получения минимальных данных пользователя для меню.
    Возвращает только username, email, full_name, initials_name.
    """
    @swagger_auto_schema(
        operation_description="Получение минимальных данных пользователя для отображения в меню.",
        responses={
            200: openapi.Response(
                description="Минимальные данные пользователя для меню.",
                schema=CMSUserMenuSerializer()
            ),
        },
        security=[{'Bearer': []}]
    )
    def get(self, request):
        touch_device_activity(request)

        serializer = CMSUserMenuSerializer(request.user)
        return Response(serializer.data, status=status.HTTP_200_OK)


class ProtectedView(BaseAPIViewAuthMixin):
    @swagger_auto_schema(
        operation_description="Защищенное представление. Проверяет валидность токена. Возвращает пустой ответ при успешной авторизации. Полные данные загружаются через /profile/.",
        responses={
            200: openapi.Response(
                description="Токен валиден, пользователь авторизован.",
                schema=openapi.Schema(
                    type=openapi.TYPE_OBJECT,
                    properties={}
                )
            ),
            401: "Неавторизованный доступ."
        },
        security=[{'Bearer': []}]
    )
    def get(self, request):
        if touch_device_activity(request) is None:
            ensure_legacy_device(request)

        UserProfile.objects.get_or_create(user=request.user)

        return Response({}, status=status.HTTP_200_OK)


class LogoutView(BaseAPIView):
    """Очистка HttpOnly refresh-cookie (доступно без валидного access)."""

    def post(self, request):
        response = Response(status=status.HTTP_204_NO_CONTENT)
        clear_auth_cookies(response)
        actor = request.user if getattr(request.user, 'is_authenticated', False) else None
        if actor is not None:
            _audit_event('auth.logout', request=request, actor=actor)
        return response
