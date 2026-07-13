"""Приём ошибок клиента и запись в logs/client-browser.log."""

from __future__ import annotations

import logging
from typing import Any

from src.config.env import env
from rest_framework import status
from rest_framework.request import Request
from rest_framework.response import Response
from src.core.utils.base.base_views import BaseAPIViewAuthMixin

logger = logging.getLogger('client.browser')

_SENSITIVE_KEYS = frozenset({
    'password', 'password_confirm', 'current_password', 'new_password', 'old_password',
    'token', 'access', 'refresh', 'authorization', 'secret', 'api_key', 'apikey',
})

_MAX_MESSAGE = 500
_MAX_CONTEXT_KEYS = 20
_MAX_CONTEXT_VALUE = 200


def _truncate(value: str, limit: int) -> str:
    if len(value) <= limit:
        return value
    return f'{value[:limit]}…'


def _is_sensitive_key(key: str) -> bool:
    lower = key.lower()
    return (
        lower in _SENSITIVE_KEYS
        or 'password' in lower
        or 'token' in lower
        or 'secret' in lower
    )


def _sanitize_context(raw: Any) -> dict[str, str]:
    if not isinstance(raw, dict):
        return {}
    sanitized: dict[str, str] = {}
    for index, (key, value) in enumerate(raw.items()):
        if index >= _MAX_CONTEXT_KEYS:
            break
        if not isinstance(key, str):
            continue
        if _is_sensitive_key(key):
            sanitized[key] = '[скрыто]'
            continue
        if value is None:
            sanitized[key] = ''
        elif isinstance(value, (str, int, float, bool)):
            sanitized[key] = _truncate(str(value), _MAX_CONTEXT_VALUE)
        else:
            sanitized[key] = _truncate(str(type(value).__name__), _MAX_CONTEXT_VALUE)
    return sanitized


class ClientBrowserLogView(BaseAPIViewAuthMixin):
    """POST sanitized client errors for server-side retention."""

    def post(self, request: Request):
        if not env.bool('CLIENT_BROWSER_LOG_ENABLED', default=True):
            return Response(status=status.HTTP_204_NO_CONTENT)

        level = str(request.data.get('level', 'error')).lower()
        if level not in {'warn', 'warning', 'error', 'critical'}:
            level = 'error'
        if level == 'warning':
            level = 'warn'

        message = request.data.get('message')
        if not isinstance(message, str) or not message.strip():
            return Response({'detail': 'message is required'}, status=status.HTTP_400_BAD_REQUEST)

        message = _truncate(message.strip(), _MAX_MESSAGE)
        context = _sanitize_context(request.data.get('context'))
        user_ref = getattr(request.user, 'public_id', None)
        path = request.data.get('path')
        if isinstance(path, str):
            path = _truncate(path.strip(), 300)
        else:
            path = ''

        log_method = logger.warning if level == 'warn' else logger.error
        if level == 'critical':
            log_method = logger.critical

        log_method(
            'user=%s path=%s context=%s message=%s',
            user_ref or request.user.pk,
            path or '-',
            context or {},
            message,
        )
        return Response(status=status.HTTP_204_NO_CONTENT)
