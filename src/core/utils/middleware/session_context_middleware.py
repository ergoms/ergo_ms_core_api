"""
Middleware session context: JWT claims платформы на request (generic).

Ядро не знает конкретных claim — их декларируют модули через контракт
``session_context.claims`` (см. session_context.py). Middleware:

- по дескрипторам ставит ``request.<request_attr>`` из payload JWT;
- при наличии ``entity_key`` + ``resolve`` — ленивое property ``request.<entity_key>``.
"""

from __future__ import annotations

import logging
from typing import Any

from src.core.integrations.session_context import (
    get_session_claim_descriptors,
    get_session_entity_resolvers,
)

logger = logging.getLogger(__name__)


def has_session_entity_resolver(entity_key: str) -> bool:
    """Есть ли зарегистрированный resolver для сущности сессии по её entity_key."""
    return callable(get_session_entity_resolvers().get(entity_key))


class SessionContextMiddleware:
    """
    JWT session context на каждый запрос (generic по дескрипторам).

    Устанавливает request.<request_attr> из токена; request.<entity_key> —
    ленивая загрузка через resolver дескриптора.

    DRF JWT-аутентификация выполняется уже во view, поэтому middleware
    читает Bearer access-токен из Authorization сам (не ждёт request.auth).
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        path = getattr(request, 'path', '') or ''
        local_only = path.startswith('/internal/')
        descriptors = get_session_claim_descriptors(local_only=local_only)

        request._session_entity_cache = {}
        request._session_entity_resolvers = {}

        for descriptor in descriptors:
            setattr(request, descriptor['request_attr'], None)

        self._extract_session_claims_from_token(request, descriptors)

        for descriptor in descriptors:
            entity_key = descriptor.get('entity_key')
            resolve = descriptor.get('resolve')
            if entity_key and callable(resolve):
                request._session_entity_resolvers[entity_key] = (
                    descriptor['request_attr'],
                    descriptor['claim'],
                    resolve,
                )
                self._ensure_entity_property(type(request), entity_key)

        return self.get_response(request)

    @staticmethod
    def _access_token_payload(request) -> Any | None:
        """Payload access JWT: request.auth (если уже есть) или Authorization Bearer."""
        auth = getattr(request, 'auth', None)
        if auth is not None and hasattr(auth, 'get'):
            return auth

        header = request.META.get('HTTP_AUTHORIZATION') or ''
        if not isinstance(header, str) or not header.startswith('Bearer '):
            return None
        raw = header[7:].strip()
        if not raw:
            return None
        try:
            from rest_framework_simplejwt.tokens import AccessToken

            return AccessToken(raw)
        except Exception:
            return None

    @staticmethod
    def _extract_session_claims_from_token(request, descriptors: list) -> None:
        payload = SessionContextMiddleware._access_token_payload(request)
        if payload is None:
            return
        try:
            for descriptor in descriptors:
                claim = descriptor['claim']
                request_attr = descriptor['request_attr']
                value = payload.get(claim)
                if value is not None:
                    setattr(request, request_attr, int(value))
        except (ValueError, TypeError, AttributeError) as exc:
            logger.warning('Ошибка извлечения session context из токена: %s', exc)

    @classmethod
    def _ensure_entity_property(cls, request_cls, entity_key: str) -> None:
        existing = getattr(request_cls, entity_key, None)
        if isinstance(existing, property):
            return
        setattr(
            request_cls,
            entity_key,
            property(lambda self, ek=entity_key: cls._load_session_entity(self, ek)),
        )

    @staticmethod
    def _load_session_entity(request, entity_key: str):
        cache = getattr(request, '_session_entity_cache', None)
        if cache is not None and entity_key in cache:
            return cache[entity_key]

        resolvers = getattr(request, '_session_entity_resolvers', {}) or {}
        entry = resolvers.get(entity_key)
        if not entry:
            return None
        request_attr, claim, resolve = entry

        entity_id = getattr(request, request_attr, None)
        if not entity_id or not callable(resolve):
            if cache is not None:
                cache[entity_key] = None
            return None

        try:
            entity = resolve(**{claim: entity_id})
        except Exception as exc:
            logger.warning(
                'Ошибка загрузки session entity %s (id=%s): %s',
                entity_key,
                entity_id,
                exc,
            )
            entity = None

        if cache is not None:
            cache[entity_key] = entity
        return entity


class SessionScopeRequiredMiddleware:
    """
    Требует наличия обязательных session-claim (required_guard) в JWT.

    Обязательные claim декларируют модули через дескриптор session-claim
    (``required_guard: True``). Не добавляется глобально — только на конкретные
    views через декоратор ``session_scope_required`` или permission
    ``RequiresSessionScope``.
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        from .session_scope import (
            missing_required_session_claims,
            session_scope_forbidden_response,
        )

        if missing_required_session_claims(request):
            return session_scope_forbidden_response(drf=False)

        return self.get_response(request)
