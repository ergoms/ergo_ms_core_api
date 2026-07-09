from django.contrib.auth import get_user_model

User = get_user_model()
from django.core.cache import cache

from src.config.env import env
from src.core.cms.adp.models import UserDevice

_DEVICE_SESSION_CACHE_TTL_SECONDS = env.int('API_DEVICE_SESSION_CACHE_TTL', default=45)
_DEVICE_ACTIVITY_DEBOUNCE_SECONDS = env.int('API_DEVICE_ACTIVITY_DEBOUNCE_SEC', default=120)

_DEVICE_SESSION_VERSION_PREFIX = 'device_session:ver:'
_DEVICE_SESSION_ACTIVE_PREFIX = 'device_session:active:'
_DEVICE_ACTIVITY_DEBOUNCE_PREFIX = 'device_activity:debounce:'


def _device_session_version_key(user_id: int) -> str:
    return f'{_DEVICE_SESSION_VERSION_PREFIX}{user_id}'


def _device_session_version(user_id: int) -> int:
    version = cache.get(_device_session_version_key(user_id))
    return int(version) if version is not None else 0


def _device_active_cache_key(user_id: int, device_pk: int) -> str:
    return f'{_DEVICE_SESSION_ACTIVE_PREFIX}{user_id}:{device_pk}:v{_device_session_version(user_id)}'


def _device_debounce_cache_key(user_id: int, device_pk: int) -> str:
    return f'{_DEVICE_ACTIVITY_DEBOUNCE_PREFIX}{user_id}:{device_pk}'


def invalidate_device_session_cache(user_id: int, device_id: int | None = None) -> None:
    if device_id is None:
        version_key = _device_session_version_key(user_id)
        cache.set(version_key, _device_session_version(user_id) + 1, timeout=None)
        return
    cache.delete(_device_active_cache_key(user_id, int(device_id)))


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
    invalidate_device_session_cache(device.user_id, device.id)
    device.delete()


def is_device_session_active(user: User, device_id) -> bool:
    if device_id is None:
        return True
    try:
        device_pk = int(device_id)
    except (TypeError, ValueError):
        return False

    cache_key = _device_active_cache_key(user.pk, device_pk)
    cached = cache.get(cache_key)
    if cached is not None:
        return bool(cached)

    result = UserDevice.objects.filter(pk=device_pk, user=user, is_active=True).exists()
    cache.set(cache_key, result, timeout=_DEVICE_SESSION_CACHE_TTL_SECONDS)
    return result


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


def ensure_legacy_device(request) -> UserDevice | None:
    """Создаёт запись устройства для старых токенов без device_id."""
    user = getattr(request, 'user', None)
    if user is None or not getattr(user, 'is_authenticated', False):
        return None

    from src.core.cms.adp.user_agent_utils import (
        build_device_display_name,
        detect_device_type,
        get_client_ip,
    )

    ip_address = get_client_ip(request)
    user_agent = request.META.get('HTTP_USER_AGENT', '')
    device_type = detect_device_type(user_agent)
    device_name = build_device_display_name(user_agent, device_type)

    from src.core.utils.geoip import resolve_ip_location

    city, country = resolve_ip_location(ip_address)
    device, _created = UserDevice.objects.update_or_create(
        user=user,
        device_name=device_name,
        ip_address=ip_address,
        defaults={
            'device_type': device_type,
            'user_agent': user_agent,
            'city': city,
            'country': country,
            'is_active': True,
        },
    )
    return device


def touch_device_activity(request) -> UserDevice | None:
    user = getattr(request, 'user', None)
    if user is None or not getattr(user, 'is_authenticated', False):
        return None

    device_id = get_request_device_id(request)
    if device_id is not None:
        device = UserDevice.objects.filter(pk=device_id, user=user, is_active=True).first()
        if device is not None:
            _touch_device_if_not_debounced(device)
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
        _touch_device_if_not_debounced(device)
        return device

    return ensure_legacy_device(request)


def _touch_device_if_not_debounced(device: UserDevice) -> None:
    debounce_key = _device_debounce_cache_key(device.user_id, device.id)
    if cache.get(debounce_key) is not None:
        return

    device.save(update_fields=['last_activity'])
    cache.set(debounce_key, 1, timeout=_DEVICE_ACTIVITY_DEBOUNCE_SECONDS)
