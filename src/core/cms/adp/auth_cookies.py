"""HttpOnly cookie для refresh-токена JWT и клиентская подсказка о наличии сессии."""

from datetime import timedelta

from django.conf import settings

REFRESH_COOKIE_NAME = 'refresh'
SESSION_HINT_COOKIE_NAME = 'ergo_session'
PREV_USER_COOKIE_NAME = 'ergo_prev_user'

# Достаточно до следующего логина в том же браузере.
PREV_USER_COOKIE_MAX_AGE = 60 * 60 * 24


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
    """Сбрасывает refresh и session-hint. Cookie предыдущего user не трогает."""
    response.delete_cookie(
        REFRESH_COOKIE_NAME,
        path='/',
        samesite=_cookie_samesite(),
    )
    clear_session_hint_cookie(response)


def set_prev_user_cookie(response, user_id, max_age_seconds: int = PREV_USER_COOKIE_MAX_AGE) -> None:
    if user_id is None or user_id == '':
        return
    response.set_cookie(
        PREV_USER_COOKIE_NAME,
        str(user_id),
        max_age=max(int(max_age_seconds), 60),
        httponly=True,
        secure=_cookie_secure(),
        samesite=_cookie_samesite(),
        path='/',
    )


def clear_prev_user_cookie(response) -> None:
    response.delete_cookie(
        PREV_USER_COOKIE_NAME,
        path='/',
        samesite=_cookie_samesite(),
    )


def get_prev_user_id_from_request(request):
    raw = request.COOKIES.get(PREV_USER_COOKIE_NAME)
    if raw is None or raw == '':
        return None
    try:
        return int(raw)
    except (TypeError, ValueError):
        return None


def ensure_session_hint_cookie(request, response, max_age_seconds: int) -> None:
    """Миграция: HttpOnly refresh есть, подсказки нет — выставляем без token-refresh."""
    if not request.COOKIES.get(REFRESH_COOKIE_NAME):
        return
    if request.COOKIES.get(SESSION_HINT_COOKIE_NAME):
        return
    set_session_hint_cookie(response, max_age_seconds)


def get_refresh_token_from_request(request) -> str | None:
    return request.COOKIES.get(REFRESH_COOKIE_NAME) or None


def refresh_cookie_max_age(refresh_lifetime: timedelta) -> int:
    return max(int(refresh_lifetime.total_seconds()), 60)
