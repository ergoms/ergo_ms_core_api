from src.config.settings.auth import REFRESH_TOKEN_LIFETIME
from src.core.cms.adp.auth_cookies import ensure_session_hint_cookie, refresh_cookie_max_age

from datetime import timedelta


class SessionHintCookieMiddleware:
    """Выставляет ergo_session=1, если есть HttpOnly refresh (миграция + первый заход после F5)."""

    def __init__(self, get_response):
        self.get_response = get_response
        self._hint_max_age = refresh_cookie_max_age(timedelta(minutes=REFRESH_TOKEN_LIFETIME))

    def __call__(self, request):
        response = self.get_response(request)
        # Logout чистит refresh в response, но request.COOKIES ещё со старым refresh —
        # ensure_* иначе снова поставит ergo_session и клиент уйдёт в restore↔logout цикл.
        if request.path.rstrip('/').endswith('/logout'):
            return response
        ensure_session_hint_cookie(request, response, self._hint_max_age)
        return response
