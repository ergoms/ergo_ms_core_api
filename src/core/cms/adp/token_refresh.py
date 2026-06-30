from rest_framework.exceptions import ValidationError
from rest_framework_simplejwt.serializers import TokenRefreshSerializer
from rest_framework_simplejwt.tokens import RefreshToken
from rest_framework_simplejwt.views import TokenRefreshView

from django.contrib.auth import get_user_model

from src.core.cms.adp.services.session_devices import is_device_session_active


class DeviceBoundTokenRefreshSerializer(TokenRefreshSerializer):
    def validate(self, attrs):
        refresh = RefreshToken(attrs['refresh'])
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
