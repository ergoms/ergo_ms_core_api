from django.contrib.auth.models import User

from src.core.cms.adp.models import UserDevice


def blacklist_refresh_jti(user: User, jti: str | None) -> None:
    if not jti:
        return

    try:
        from rest_framework_simplejwt.token_blacklist.models import BlacklistedToken, OutstandingToken

        outstanding = OutstandingToken.objects.get(jti=jti, user=user)
        BlacklistedToken.objects.get_or_create(token=outstanding)
    except OutstandingToken.DoesNotExist:
        pass
    except Exception:
        pass


def bind_device_to_refresh_token(device: UserDevice, refresh_token) -> None:
    jti = refresh_token.payload.get('jti')
    if not jti:
        return

    if device.outstanding_token_jti and device.outstanding_token_jti != jti:
        blacklist_refresh_jti(device.user, device.outstanding_token_jti)

    device.outstanding_token_jti = jti
    device.is_active = True
    device.save(update_fields=['outstanding_token_jti', 'is_active'])


def attach_device_claim(access_token, device: UserDevice) -> None:
    access_token['device_id'] = device.id


def attach_device_to_refresh_token(refresh_token, device: UserDevice) -> None:
    refresh_token['device_id'] = device.id


def revoke_user_device_session(device: UserDevice) -> None:
    blacklist_refresh_jti(device.user, device.outstanding_token_jti)
    device.delete()


def is_device_session_active(user: User, device_id) -> bool:
    if device_id is None:
        return True
    try:
        device_pk = int(device_id)
    except (TypeError, ValueError):
        return False
    return UserDevice.objects.filter(pk=device_pk, user=user, is_active=True).exists()


def get_request_device_id(request) -> int | None:
    token = getattr(request, 'auth', None)
    if token is None:
        return None
    payload = getattr(token, 'payload', token)
    if not hasattr(payload, 'get'):
        return None
    device_id = payload.get('device_id')
    if device_id is None:
        return None
    try:
        return int(device_id)
    except (TypeError, ValueError):
        return None


def is_current_device(request, device: UserDevice) -> bool:
    device_id = get_request_device_id(request)
    if device_id is not None:
        return device.id == device_id
    from src.core.cms.adp.user_agent_utils import get_client_ip

    return str(device.ip_address) == get_client_ip(request)


def touch_device_activity(request) -> UserDevice | None:
    user = getattr(request, 'user', None)
    if user is None or not getattr(user, 'is_authenticated', False):
        return None

    device_id = get_request_device_id(request)
    if device_id is not None:
        device = UserDevice.objects.filter(pk=device_id, user=user, is_active=True).first()
        if device is not None:
            device.save(update_fields=['last_activity'])
        return device

    from src.core.cms.adp.user_agent_utils import get_client_ip

    ip_address = get_client_ip(request)
    user_agent = request.META.get('HTTP_USER_AGENT', '')
    device = UserDevice.objects.filter(
        user=user,
        ip_address=ip_address,
        user_agent=user_agent,
        is_active=True,
    ).first()
    if device is not None:
        device.save(update_fields=['last_activity'])
    return device
