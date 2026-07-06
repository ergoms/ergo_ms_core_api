"""Request-scoped кэш для PermissionService (один HTTP-запрос — один набор запросов к БД)."""

from __future__ import annotations

import contextvars

_permission_cache: contextvars.ContextVar[dict | None] = contextvars.ContextVar(
    'ergo_permission_cache',
    default=None,
)


def get_request_permission_cache() -> dict:
    cache = _permission_cache.get()
    if cache is None:
        cache = {}
        _permission_cache.set(cache)
    return cache


def clear_request_permission_cache() -> None:
    _permission_cache.set({})


class PermissionRequestCacheMiddleware:
    """Инициализирует пустой кэш прав на время обработки запроса."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        token = _permission_cache.set({})
        try:
            return self.get_response(request)
        finally:
            _permission_cache.reset(token)
