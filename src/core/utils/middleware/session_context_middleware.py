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
    collect_session_jwt_claims,
    get_required_guard_claims,
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

    Размещать ПОСЛЕ AuthenticationMiddleware и JWT authentication.
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        descriptors = get_session_claim_descriptors()

        request._session_entity_cache = {}
        request._session_entity_resolvers = {}

        for descriptor in descriptors:
            setattr(request, descriptor['request_attr'], None)

        self._extract_session_claims_from_token(request)

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
    def _extract_session_claims_from_token(request) -> None:
        if not hasattr(request, 'auth') or not request.auth:
            return
        try:
            for claim in collect_session_jwt_claims():
                value = request.auth.get(claim)
                if value is not None:
                    setattr(request, claim, int(value))
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
    views через декоратор.
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        required = get_required_guard_claims()
        missing = [claim for claim in required if not getattr(request, claim, None)]
        if missing:
            from rest_framework import status
            from rest_framework.response import Response

            return Response(
                {
                    'error': (
                        'Требуется активный контекст сессии. '
                        'Выполните вход в нужный контекст.'
                    ),
                },
                status=status.HTTP_403_FORBIDDEN,
            )

        return self.get_response(request)
