from rest_framework.exceptions import AuthenticationFailed
from rest_framework_simplejwt.authentication import JWTAuthentication

from src.core.cms.adp.services.session_devices import is_device_session_active


class DeviceBoundJWTAuthentication(JWTAuthentication):
    """
    JWT-аутентификация с проверкой активной сессии устройства.
    Токены без claim device_id (старые) принимаются до истечения срока.
    """

    def get_user(self, validated_token):
        user = super().get_user(validated_token)
        device_id = validated_token.get('device_id')
        if device_id is None:
            return user
        if not is_device_session_active(user, device_id):
            raise AuthenticationFailed('Сессия завершена. Войдите снова.')
        return user
