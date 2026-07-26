"""
Контракт session context платформы — единый дескриптор session-claims.

Модуль декларирует свои session-claims одним дескриптором в группе
``session_context.claims``::

    bridge.provide_many('session_context.claims', key='my_scope', obj={
        'claim': 'my_scope_id',        # ключ в payload JWT
        'request_attr': 'my_scope_id', # атрибут на request (по умолчанию = claim)
        'entity_key': 'my_scope',      # имя ленивого request.my_scope
        'resolve': load_my_scope,      # (my_scope_id=..., **kw) -> entity | None
        'required_guard': True,        # RequiresSessionScope / session_scope_required
    })

Ядро выводит из дескрипторов список JWT claims, карту ``entity_key -> resolve``,
карту ``entity_key -> claim`` и набор claims с ``required_guard``.
"""

from __future__ import annotations

from typing import Any, Callable

from src.core.integrations import bridge
from src.core.integrations.module_contracts import SESSION_CLAIMS_GROUP

__all__ = (
    'SESSION_CLAIMS_GROUP',
    'get_session_claim_descriptors',
    'collect_session_jwt_claims',
    'get_session_entity_resolvers',
    'get_session_entity_claim_keys',
    'get_required_guard_claims',
    'reset_session_context_cache',
)

_descriptors_cache: list[dict] | None = None


def _normalize_descriptor(key: str, raw: Any) -> dict | None:
    """Приводит сырой дескриптор к каноническому виду или отбрасывает невалидный."""
    if not isinstance(raw, dict):
        return None
    claim = raw.get('claim')
    if not claim or not isinstance(claim, str):
        return None
    request_attr = raw.get('request_attr') or claim
    entity_key = raw.get('entity_key') or None
    resolve = raw.get('resolve')
    return {
        'key': key,
        'claim': claim,
        'request_attr': str(request_attr),
        'entity_key': str(entity_key) if entity_key else None,
        'resolve': resolve if callable(resolve) else None,
        'required_guard': bool(raw.get('required_guard', False)),
    }


def get_session_claim_descriptors() -> list[dict]:
    """Все session-claim дескрипторы из контракта session_context.claims."""
    global _descriptors_cache
    if _descriptors_cache is not None:
        return _descriptors_cache

    by_claim: dict[str, dict] = {}

    for key, raw in bridge.all(SESSION_CLAIMS_GROUP).items():
        descriptor = _normalize_descriptor(str(key), raw)
        if descriptor is None:
            continue
        existing = by_claim.get(descriptor['claim'])
        if existing is None:
            by_claim[descriptor['claim']] = descriptor
            continue
        if not existing.get('entity_key') and descriptor.get('entity_key'):
            existing['entity_key'] = descriptor['entity_key']
        if not existing.get('resolve') and descriptor.get('resolve'):
            existing['resolve'] = descriptor['resolve']
        if descriptor.get('required_guard'):
            existing['required_guard'] = True

    _descriptors_cache = list(by_claim.values())
    return _descriptors_cache


def collect_session_jwt_claims() -> tuple[str, ...]:
    """Список claim, которые ядро читает с JWT в request."""
    return tuple(d['claim'] for d in get_session_claim_descriptors())


def get_session_entity_resolvers() -> dict[str, Callable]:
    """entity_key → resolver (для ленивой загрузки ORM-сущности из claim)."""
    return {
        d['entity_key']: d['resolve']
        for d in get_session_claim_descriptors()
        if d.get('entity_key') and callable(d.get('resolve'))
    }


def get_session_entity_claim_keys() -> dict[str, str]:
    """entity_key → claim (имя атрибута на request с id сущности)."""
    return {
        d['entity_key']: d['request_attr']
        for d in get_session_claim_descriptors()
        if d.get('entity_key')
    }


def get_required_guard_claims() -> tuple[str, ...]:
    """claim с флагом required_guard (RequiresSessionScope / session_scope_required)."""
    return tuple(
        d['request_attr']
        for d in get_session_claim_descriptors()
        if d.get('required_guard')
    )


def reset_session_context_cache() -> None:
    """Сброс кеша дескрипторов (тесты, регистрация после старта)."""
    global _descriptors_cache
    _descriptors_cache = None
