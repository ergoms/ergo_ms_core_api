"""JWT-principal без чтения auth_user (уровень 3)."""

from __future__ import annotations

from types import SimpleNamespace
from uuid import UUID

from rest_framework.exceptions import AuthenticationFailed
from rest_framework_simplejwt.authentication import JWTAuthentication

from src.core.cms.adp.services.session_devices import is_device_session_active
from src.core.integrations import bridge
from src.core.integrations.module_contracts import SESSION_DEVICE_ACTIVE


def _jwt_claims_mode() -> bool:
    from django.conf import settings

    mode = (getattr(settings, 'MODULE_AUTH_MODE', 'orm') or 'orm').strip().lower()
    return mode == 'jwt_claims'


def _as_uuid(value):
    if not value:
        return None
    try:
        return UUID(str(value))
    except (TypeError, ValueError):
        return None


def _device_active_snapshot(active):
    """False/None — отказ. True или dict со ``active`` — снимок (старый bool без public_id)."""
    if active is None or active is False:
        return None
    if isinstance(active, dict):
        if not active.get('active', True):
            return None
        return active
    if active:
        return {}
    return None


class JwtPrincipal(SimpleNamespace):
    """Лёгкий пользователь из JWT (без ORM)."""

    is_authenticated = True
    is_active = True
    is_anonymous = False
    is_staff = False
    is_superuser = False

    def __str__(self) -> str:
        return str(getattr(self, 'username', '') or getattr(self, 'public_id', '') or self.pk)


# Повторный разбор JWT в DRF после ApiAccessPolicyMiddleware.
REQUEST_JWT_AUTH_ATTR = '_ergo_jwt_auth'


class DeviceBoundJWTAuthentication(JWTAuthentication):
    """
    JWT с проверкой device_id.

    MODULE_AUTH_MODE=orm (по умолчанию) — пользователь из БД ядра.
    MODULE_AUTH_MODE=jwt_claims — principal из claims, устройство и активность
    пользователя только через мост ``session.device_active``. Без ответа моста —
    отказ, без запасного чтения ORM.
    """

    def authenticate(self, request):
        cached = getattr(request, REQUEST_JWT_AUTH_ATTR, None)
        if cached is not None:
            return cached
        result = super().authenticate(request)
        if result is not None:
            setattr(request, REQUEST_JWT_AUTH_ATTR, result)
        return result

    def get_user(self, validated_token):
        device_id = validated_token.get('device_id')
        if device_id is None:
            raise AuthenticationFailed('Сессия завершена. Войдите снова.')

        if _jwt_claims_mode():
            return self._principal_from_claims(validated_token, device_id)

        user = super().get_user(validated_token)
        if not is_device_session_active(user, device_id):
            raise AuthenticationFailed('Сессия завершена. Войдите снова.')
        return user

    def _principal_from_claims(self, validated_token, device_id):
        user_id = validated_token.get('user_id')
        public_id = validated_token.get('user_public_id')
        if user_id is None and not public_id:
            raise AuthenticationFailed('Сессия завершена. Войдите снова.')

        snapshot = _device_active_snapshot(
            bridge.call(
                SESSION_DEVICE_ACTIVE,
                user_id=user_id,
                device_id=device_id,
                user_public_id=str(public_id) if public_id else '',
                default=None,
            )
        )
        if snapshot is None:
            raise AuthenticationFailed('Сессия завершена. Войдите снова.')

        pk = int(user_id) if user_id is not None else 0
        pid = _as_uuid(public_id) or _as_uuid(snapshot.get('user_public_id'))
        username = str(validated_token.get('username') or snapshot.get('username') or '')
        raw_super = validated_token.get('is_superuser')
        raw_staff = validated_token.get('is_staff')
        is_superuser = bool(raw_super) if raw_super is not None else bool(snapshot.get('is_superuser'))
        is_staff = bool(raw_staff) if raw_staff is not None else bool(snapshot.get('is_staff'))
        return JwtPrincipal(
            id=pk,
            pk=pk,
            public_id=pid,
            username=username,
            is_superuser=is_superuser,
            is_staff=is_staff,
        )
