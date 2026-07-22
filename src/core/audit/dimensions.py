"""Измерения аудита (scope), расширяемые модулями.

Модуль декларирует своё измерение журнала через bridge-группу
``audit.scope_dimensions`` дескриптором::

    bridge.provide_many('audit.scope_dimensions', key='my_dim', obj={
        'key': 'my_dim',
        'label': 'Моё измерение',
        'resolve': lambda request: getattr(request, 'my_dim_id', None),
        'filter_param': 'my_dim_id',   # имя query-параметра в UI
        'indexed': True,                # горячее измерение
        'read_guard': True,             # ограничивает чтение журнала не-админам
    })

Ядро не знает конкретных измерений — оно агрегирует дескрипторы, складывает
значения в ``AuditEvent.scope`` (JSON) и строит фильтры/справочник для UI.

``read_guard`` помечает измерение, которое обязательно ограничивает выборку
журнала для не-администраторов (например, событие видно только в рамках своего
контекста). Без единого read_guard-измерения не-админ журнал не видит.
"""

from __future__ import annotations

import logging

from src.core.integrations import bridge
from src.core.integrations.module_contracts import AUDIT_SCOPE_DIMENSIONS_GROUP

logger = logging.getLogger('core.audit')

_dimensions_cache: list[dict] | None = None


def _normalize(key: str, raw) -> dict | None:
    if not isinstance(raw, dict):
        return None
    dim_key = raw.get('key') or key
    if not dim_key:
        return None
    resolve = raw.get('resolve')
    return {
        'key': str(dim_key),
        'label': raw.get('label') or str(dim_key),
        'resolve': resolve if callable(resolve) else None,
        'filter_param': raw.get('filter_param') or f'{dim_key}_id',
        'indexed': bool(raw.get('indexed', False)),
        'read_guard': bool(raw.get('read_guard', False)),
    }


def get_scope_dimensions() -> list[dict]:
    """Зарегистрированные измерения аудита (нормализованные, кэш in-process)."""
    global _dimensions_cache
    if _dimensions_cache is not None:
        return _dimensions_cache

    result: list[dict] = []
    for key, raw in bridge.all(AUDIT_SCOPE_DIMENSIONS_GROUP).items():
        descriptor = _normalize(str(key), raw)
        if descriptor is not None:
            result.append(descriptor)
    _dimensions_cache = result
    return _dimensions_cache


def get_read_guard_dimensions() -> list[dict]:
    """Измерения с флагом read_guard (ограничивают чтение журнала не-админам)."""
    return [d for d in get_scope_dimensions() if d.get('read_guard')]


def reset_scope_dimensions_cache() -> None:
    global _dimensions_cache
    _dimensions_cache = None


def resolve_scope(request) -> dict:
    """Собрать значения всех измерений из запроса: {key: value}."""
    if request is None:
        return {}
    scope: dict = {}
    for dim in get_scope_dimensions():
        resolve = dim.get('resolve')
        if not callable(resolve):
            continue
        try:
            value = resolve(request)
        except Exception as exc:
            logger.warning('Ошибка resolve измерения аудита %s: %s', dim['key'], exc)
            value = None
        if value is not None:
            scope[dim['key']] = value
    return scope


def get_dimensions_for_ui() -> list[dict]:
    """Список измерений для клиента (без callable)."""
    return [
        {'key': d['key'], 'label': d['label'], 'filter_param': d['filter_param']}
        for d in get_scope_dimensions()
    ]
