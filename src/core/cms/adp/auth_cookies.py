"""HttpOnly cookie для refresh-токена JWT и клиентская подсказка о наличии сессии."""

from datetime import timedelta

from django.conf import settings

REFRESH_COOKIE_NAME = 'refresh'
SESSION_HINT_COOKIE_NAME = 'ergo_session'


def _cookie_secure() -> bool:
    return bool(getattr(settings, 'SESSION_COOKIE_SECURE', False))


def _cookie_samesite():
    return getattr(settings, 'SESSION_COOKIE_SAMESITE', 'Lax')


def set_session_hint_cookie(response, max_age_seconds: int) -> None:
    """Не HttpOnly: клиент проверяет перед token-refresh, чтобы не слать лишние 400."""
    response.set_cookie(
        SESSION_HINT_COOKIE_NAME,
        '1',
        max_age=max_age_seconds,
        httponly=False,
        secure=_cookie_secure(),
        samesite=_cookie_samesite(),
        path='/',
    )


def clear_session_hint_cookie(response) -> None:
    response.delete_cookie(
        SESSION_HINT_COOKIE_NAME,
        path='/',
        samesite=_cookie_samesite(),
    )


def set_refresh_cookie(response, refresh_token: str, max_age_seconds: int) -> None:
    response.set_cookie(
        REFRESH_COOKIE_NAME,
        refresh_token,
        max_age=max_age_seconds,
        httponly=True,
        secure=_cookie_secure(),
        samesite=_cookie_samesite(),
        path='/',
    )
    set_session_hint_cookie(response, max_age_seconds)


def clear_auth_cookies(response) -> None:
    response.delete_cookie(
        REFRESH_COOKIE_NAME,
        path='/',
        samesite=_cookie_samesite(),
    )
    clear_session_hint_cookie(response)


def ensure_session_hint_cookie(request, response, max_age_seconds: int) -> None:
    """Миграция: HttpOnly refresh есть, подсказки нет — выставляем без token-refresh."""
    if not request.COOKIES.get(REFRESH_COOKIE_NAME):
        return
    if request.COOKIES.get(SESSION_HINT_COOKIE_NAME):
        return
    set_session_hint_cookie(response, max_age_seconds)


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
