from rest_framework.response import Response
from rest_framework import status
from drf_yasg.utils import swagger_auto_schema
from drf_yasg import openapi

from django.contrib.auth.models import User
import logging

from src.core.cms.adp.models import UserDevice, UserProfile
from src.core.cms.adp.serializers import (
    ChangePasswordSerializer,
    UserDeviceSerializer,
    CMSUserSerializer,
    CMSUserMenuSerializer,
    UpdateUserProfileSerializer,
)
from src.core.utils.base.base_views import BaseAPIView, BaseAPIViewAuthMixin
from src.core.cms.adp.services.profile_settings import ProfileSettingsService
from src.core.utils.methods import parse_errors_to_dict
from src.core.cms.adp.services.session_devices import (
    ensure_legacy_device,
    is_current_device,
    revoke_user_device_session,
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


class ChangePasswordView(BaseAPIViewAuthMixin):
    @swagger_auto_schema(
        operation_description="Смена пароля пользователя.",
        request_body=openapi.Schema(
            type=openapi.TYPE_OBJECT,
            properties={
                'current_password': openapi.Schema(
                    type=openapi.TYPE_STRING,
                    format=openapi.FORMAT_PASSWORD,
                    description='Текущий пароль'
                ),
                'new_password': openapi.Schema(
                    type=openapi.TYPE_STRING,
                    format=openapi.FORMAT_PASSWORD,
                    description='Новый пароль'
                ),
                'confirm_password': openapi.Schema(
                    type=openapi.TYPE_STRING,
                    format=openapi.FORMAT_PASSWORD,
                    description='Подтверждение нового пароля'
                ),
            },
            required=['current_password', 'new_password', 'confirm_password'],
        ),
        responses={
            200: "Пароль успешно изменён.",
            400: "Ошибка валидации данных."
        },
        security=[{'Bearer': []}]
    )
    def post(self, request):
        touch_device_activity(request)

        serializer = ChangePasswordSerializer(data=request.data, context={'request': request})
        
        if serializer.is_valid():
            user = request.user
            user.set_password(serializer.validated_data['new_password'])
            user.save()

            _audit_event('user.password_changed', request=request, actor=user, severity='security',
                         entity={'type': 'user', 'label': user.get_full_name() or user.username})

            return Response(
                {"message": "Пароль успешно изменён."}, 
                status=status.HTTP_200_OK
            )
        
        errors = parse_errors_to_dict(serializer.errors)
        return Response(
            errors, 
            status=status.HTTP_400_BAD_REQUEST
        )


class UserDevicesView(BaseAPIViewAuthMixin):
    @swagger_auto_schema(
        operation_description="Получение списка устройств пользователя.",
        responses={
            200: openapi.Response(
                description="Список устройств пользователя.",
                schema=UserDeviceSerializer(many=True)
            ),
        },
        security=[{'Bearer': []}]
    )
    def get(self, request):
        touch_device_activity(request)

        devices = (
            UserDevice.objects
            .filter(user=request.user, is_active=True)
            .order_by('-last_activity')
        )
        serializer = UserDeviceSerializer(
            devices,
            many=True,
            context={'request': request},
        )
        return Response(serializer.data, status=status.HTTP_200_OK)


class UserDeviceDetailView(BaseAPIViewAuthMixin):
    @swagger_auto_schema(
        operation_description="Удаление устройства пользователя (завершение сессии).",
        responses={
            200: "Устройство успешно удалено.",
            404: "Устройство не найдено."
        },
        security=[{'Bearer': []}]
    )
    def delete(self, request, device_id):
        try:
            device = UserDevice.objects.get(id=device_id, user=request.user)
            if is_current_device(request, device):
                return Response(
                    {'error': 'Нельзя завершить текущую сессию'},
                    status=status.HTTP_400_BAD_REQUEST,
                )
            revoke_user_device_session(device)
            return Response(
                {"message": "Сессия завершена."},
                status=status.HTTP_200_OK
            )
        except UserDevice.DoesNotExist:
            return Response(
                {"error": "Устройство не найдено."}, 
                status=status.HTTP_404_NOT_FOUND
            )

class UserProfileView(BaseAPIViewAuthMixin):
    @swagger_auto_schema(
        operation_description="Получение профиля текущего пользователя.",
        responses={
            200: openapi.Response(
                description="Данные профиля пользователя.",
                schema=CMSUserSerializer()
            ),
        },
        security=[{'Bearer': []}]
    )
    def get(self, request):
        # Создаем профиль если его нет
        profile, created = UserProfile.objects.get_or_create(user=request.user)
        
        serializer = CMSUserSerializer(request.user)
        return Response(serializer.data, status=status.HTTP_200_OK)
    
    @swagger_auto_schema(
        operation_description="Обновление профиля пользователя.",
        request_body=UpdateUserProfileSerializer,
        responses={
            200: "Профиль успешно обновлен.",
            400: "Ошибка валидации данных."
        },
        security=[{'Bearer': []}]
    )
    def put(self, request):
        blocked_profile_fields = ProfileSettingsService.get_blocked_profile_fields(request.data, request.user)
        if blocked_profile_fields:
            return Response(
                {
                    'error': ProfileSettingsService.get_self_edit_disabled_message(),
                    'blocked_fields': sorted(blocked_profile_fields),
                },
                status=status.HTTP_403_FORBIDDEN,
            )

        # Создаем профиль если его нет
        profile, created = UserProfile.objects.get_or_create(user=request.user)
        
        serializer = UpdateUserProfileSerializer(profile, data=request.data, partial=True)
        
        if serializer.is_valid():
            serializer.save()

            user = User.objects.select_related('adp_profile').get(pk=request.user.pk)
            user_serializer = CMSUserSerializer(user)
            return Response(user_serializer.data, status=status.HTTP_200_OK)
        
        errors = parse_errors_to_dict(serializer.errors)
        return Response(errors, status=status.HTTP_400_BAD_REQUEST)

class UserSecuritySettingsView(BaseAPIViewAuthMixin):
    @swagger_auto_schema(
        operation_description="Получение настроек безопасности пользователя.",
        responses={
            200: openapi.Response(
                description="Настройки безопасности.",
                schema=openapi.Schema(
                    type=openapi.TYPE_OBJECT,
                    properties={
                        'two_factor_enabled': openapi.Schema(type=openapi.TYPE_BOOLEAN),
                        'email_notifications': openapi.Schema(type=openapi.TYPE_BOOLEAN),
                        'push_notifications': openapi.Schema(type=openapi.TYPE_BOOLEAN),
                        'sms_notifications': openapi.Schema(type=openapi.TYPE_BOOLEAN),
                        'profile_visibility': openapi.Schema(type=openapi.TYPE_STRING),
                    }
                )
            ),
        },
        security=[{'Bearer': []}]
    )
    def get(self, request):
        # Создаем профиль если его нет
        profile, created = UserProfile.objects.get_or_create(user=request.user)
        
        security_data = {
            'two_factor_enabled': profile.two_factor_enabled,
            'email_notifications': profile.email_notifications,
            'push_notifications': profile.push_notifications,
            'sms_notifications': profile.sms_notifications,
            'profile_visibility': profile.profile_visibility,
        }
        
        return Response(security_data, status=status.HTTP_200_OK)
    
    @swagger_auto_schema(
        operation_description=(
            "Обновление настроек безопасности. "
            "Поле email_notifications устарело: управление каналами уведомлений — "
            "через PATCH /notifications/preferences/ (панель «Уведомления»)."
        ),
        request_body=openapi.Schema(
            type=openapi.TYPE_OBJECT,
            properties={
                'two_factor_enabled': openapi.Schema(type=openapi.TYPE_BOOLEAN),
                'push_notifications': openapi.Schema(type=openapi.TYPE_BOOLEAN),
                'sms_notifications': openapi.Schema(type=openapi.TYPE_BOOLEAN),
                'profile_visibility': openapi.Schema(type=openapi.TYPE_STRING),
            }
        ),
        responses={
            200: "Настройки безопасности обновлены.",
            400: "Ошибка валидации данных."
        },
        security=[{'Bearer': []}]
    )
    def put(self, request):
        # Создаем профиль если его нет
        profile, created = UserProfile.objects.get_or_create(user=request.user)

        # email_notifications исключён: источник истины — NotificationPreference
        # (sentinel-строка '*'/'*'), редактируется через панель «Уведомления».
        for field in ['two_factor_enabled', 'push_notifications',
                      'sms_notifications', 'profile_visibility']:
            if field in request.data:
                setattr(profile, field, request.data[field])

        profile.save()

        return Response({"message": "Настройки безопасности обновлены."}, status=status.HTTP_200_OK)


