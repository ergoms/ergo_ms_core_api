from rest_framework import serializers
from rest_framework.exceptions import ValidationError
from rest_framework_simplejwt.serializers import TokenRefreshSerializer
from rest_framework_simplejwt.tokens import RefreshToken
from rest_framework_simplejwt.views import TokenRefreshView

from django.contrib.auth import get_user_model

from datetime import timedelta

from src.core.cms.adp.auth_cookies import (
    get_refresh_token_from_request,
    refresh_cookie_max_age,
    set_refresh_cookie,
)
from src.core.cms.adp.services.session_devices import is_device_session_active
from src.config.settings.auth import REFRESH_TOKEN_LIFETIME


class DeviceBoundTokenRefreshSerializer(TokenRefreshSerializer):
    # refresh опционален в теле — источник HttpOnly cookie (или legacy body при миграции)
    refresh = serializers.CharField(required=False, allow_blank=True)

    def validate(self, attrs):
        refresh_value = get_refresh_token_from_request(self.context['request'])
        if not refresh_value:
            raise ValidationError('Refresh token отсутствует.')
        attrs['refresh'] = refresh_value

        refresh = RefreshToken(refresh_value)
        device_id = refresh.payload.get('device_id')
        user_id = refresh.payload.get('user_id')

        if user_id is not None:
            user = get_user_model().objects.filter(pk=user_id).first()
            if user is None:
                raise ValidationError('Сессия завершена. Войдите снова.')
            if device_id is not None and not is_device_session_active(user, device_id):
                raise ValidationError('Сессия завершена. Войдите снова.')

        try:
            data = super().validate(attrs)
        except get_user_model().DoesNotExist:
            raise ValidationError('Сессия завершена. Войдите снова.') from None

        if device_id is None:
            return data

        access = refresh.access_token
        access['device_id'] = device_id
        data['access'] = str(access)
        return data


class DeviceBoundTokenRefreshView(TokenRefreshView):
    serializer_class = DeviceBoundTokenRefreshSerializer

    def post(self, request, *args, **kwargs):
        response = super().post(request, *args, **kwargs)
        if response.status_code == 200 and isinstance(response.data, dict):
            refresh_value = response.data.get('refresh') or get_refresh_token_from_request(request)
            if refresh_value:
                set_refresh_cookie(
                    response,
                    refresh_value,
                    refresh_cookie_max_age(timedelta(minutes=REFRESH_TOKEN_LIFETIME)),
                )
        return response
