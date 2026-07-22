"""Контекст текущего запроса для аудита.

Ядро само подхватывает IP, User-Agent, request_id, измерения (scope) и
инициатора из активного запроса — модулям не нужно передавать эти данные вручную.

Механика:
- `AuditContextMiddleware` кладёт в contextvar ссылку на request и сетевые
  атрибуты. Значения actor / scope читаются лениво в момент записи, потому что
  DRF аутентифицирует пользователя уже внутри view (после middleware).
"""

from __future__ import annotations

import contextvars
import uuid
from typing import Any

from .dimensions import resolve_scope

_audit_ctx: contextvars.ContextVar[dict | None] = contextvars.ContextVar(
    'ergo_audit_ctx', default=None
)


def _extract_user(request) -> Any:
    user = getattr(request, 'user', None)
    if user is not None and getattr(user, 'is_authenticated', False):
        return user
    return None


def resolve_context(request=None) -> dict:
    """Собирает контекст аудита.

    Приоритет источников:
      1. Явно переданный `request` (например, из view).
      2. request из contextvar (установлен middleware).
    Возвращает dict с ключами actor, scope (generic-измерения),
    ip_address, user_agent, request_id.
    """
    ctx = _audit_ctx.get() or {}
    req = request or ctx.get('request')

    actor = _extract_user(req) if req is not None else None
    scope = resolve_scope(req) if req is not None else {}

    return {
        'actor': actor,
        'scope': scope,
        'ip_address': ctx.get('ip_address'),
        'user_agent': ctx.get('user_agent', ''),
        'request_id': ctx.get('request_id', ''),
    }


class AuditContextMiddleware:
    """Кладёт текущий запрос и сетевые атрибуты в contextvar на время обработки."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        token = _audit_ctx.set({
            'request': request,
            'ip_address': self._client_ip(request),
            'user_agent': (request.META.get('HTTP_USER_AGENT') or '')[:512],
            'request_id': request.META.get('HTTP_X_REQUEST_ID') or uuid.uuid4().hex,
        })
        try:
            return self.get_response(request)
        finally:
            _audit_ctx.reset(token)

    @staticmethod
    def _client_ip(request) -> str | None:
        forwarded = request.META.get('HTTP_X_FORWARDED_FOR')
        if forwarded:
            return forwarded.split(',')[0].strip() or None
        return (request.META.get('REMOTE_ADDR') or '').strip() or None
