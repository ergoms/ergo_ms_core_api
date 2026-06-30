"""HttpOnly cookie для refresh-токена JWT."""

from datetime import timedelta

from django.conf import settings

REFRESH_COOKIE_NAME = 'refresh'


def _cookie_secure() -> bool:
    return bool(getattr(settings, 'SESSION_COOKIE_SECURE', False))


def set_refresh_cookie(response, refresh_token: str, max_age_seconds: int) -> None:
    response.set_cookie(
        REFRESH_COOKIE_NAME,
        refresh_token,
        max_age=max_age_seconds,
        httponly=True,
        secure=_cookie_secure(),
        samesite=getattr(settings, 'SESSION_COOKIE_SAMESITE', 'Lax'),
        path='/',
    )


def clear_auth_cookies(response) -> None:
    response.delete_cookie(
        REFRESH_COOKIE_NAME,
        path='/',
        samesite=getattr(settings, 'SESSION_COOKIE_SAMESITE', 'Lax'),
    )


def get_refresh_token_from_request(request) -> str | None:
    cookie_value = request.COOKIES.get(REFRESH_COOKIE_NAME)
    if cookie_value:
        return cookie_value
    body_refresh = getattr(request, 'data', None)
    if isinstance(body_refresh, dict):
        return body_refresh.get('refresh')
    return None


def refresh_cookie_max_age(refresh_lifetime: timedelta) -> int:
    return max(int(refresh_lifetime.total_seconds()), 60)
