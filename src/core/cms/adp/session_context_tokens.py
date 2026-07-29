"""
JWT-токены с произвольными session-claim в payload.

Ядро не знает конкретных claim — их кладёт в токен модуль-владелец домена
через ``create_scoped_session_tokens(user, **claims)``.
Access-токен наследует claims из refresh.
"""

from __future__ import annotations

from datetime import timedelta
from typing import TYPE_CHECKING

from rest_framework.exceptions import AuthenticationFailed
from rest_framework_simplejwt.tokens import RefreshToken

if TYPE_CHECKING:
    from src.core.cms.adp.models import UserDevice


class ScopedSessionRefreshToken(RefreshToken):
    """RefreshToken с произвольными session-claim в payload."""

    @classmethod
    def for_user_with_claims(cls, user, **claims):
        token = cls.for_user(user)
        for key, value in claims.items():
            if value is not None:
                token[key] = value
        return token


def create_scoped_session_tokens(
    user,
    *,
    access_lifetime: timedelta | None = None,
    refresh_lifetime: timedelta | None = None,
    device: UserDevice | None = None,
    **claims,
) -> dict[str, str]:
    """
    Пара access/refresh с session-claim в payload.

    Если передан ``device``, токены привязываются к сессии устройства
    (claim ``device_id``) — иначе DeviceBoundJWTAuthentication отклонит access.

    Returns:
        {'access': str, 'refresh': str}
    """
    from src.core.cms.adp.services.session_devices import (
        attach_device_claim,
        attach_device_to_refresh_token,
        bind_device_to_refresh_token,
    )

    refresh = ScopedSessionRefreshToken.for_user_with_claims(user, **claims)

    if refresh_lifetime:
        refresh.set_exp(lifetime=refresh_lifetime)

    access = refresh.access_token

    if access_lifetime:
        access.set_exp(lifetime=access_lifetime)

    if device is not None:
        bind_device_to_refresh_token(device, refresh)
        attach_device_to_refresh_token(refresh, device)
        attach_device_claim(access, device)

    return {
        'access': str(access),
        'refresh': str(refresh),
    }


def reissue_scoped_session_tokens(
    request,
    user,
    *,
    access_lifetime: timedelta | None = None,
    refresh_lifetime: timedelta | None = None,
    **claims,
) -> dict[str, str]:
    """
    Перевыпуск scoped-токенов с сохранением привязки к текущему устройству.

    Используется при смене session-claim (вход/выход из scope), когда
    новый JWT должен остаться валидным для DeviceBoundJWTAuthentication.
    """
    from src.core.cms.adp.models import UserDevice
    from src.core.cms.adp.services.session_devices import get_request_device_id

    device_id = get_request_device_id(request)
    if device_id is None:
        raise AuthenticationFailed('Сессия завершена. Войдите снова.')

    device = UserDevice.objects.filter(
        pk=device_id,
        user=user,
        is_active=True,
    ).first()
    if device is None:
        raise AuthenticationFailed('Сессия завершена. Войдите снова.')

    return create_scoped_session_tokens(
        user,
        access_lifetime=access_lifetime,
        refresh_lifetime=refresh_lifetime,
        device=device,
        **claims,
    )


def get_claim_from_token(token_payload, claim_key: str):
    if not token_payload:
        return None
    return token_payload.get(claim_key)
