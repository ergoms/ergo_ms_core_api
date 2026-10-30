"""Отдача снимка мониторинга без сборки в потоке HTTP-запроса."""

from __future__ import annotations

import logging
from typing import Any, Callable

from django.conf import settings
from django.core.cache import caches
from django.utils import timezone

from .runs import is_claimed, patch_status_payload

logger = logging.getLogger('src.core.source_monitor')

DEFAULT_SNAPSHOT_TTL = 60
DEFAULT_MAX_AGE = 15


def _store():
    if 'live' in settings.CACHES:
        return caches['live']
    return caches['default']


def store_snapshot(cache_key: str, payload: dict[str, Any], ttl: int = DEFAULT_SNAPSHOT_TTL) -> None:
    if not cache_key or not isinstance(payload, dict):
        return
    try:
        _store().set(
            cache_key,
            {'stored_at': timezone.now().timestamp(), 'payload': payload},
            max(1, int(ttl)),
        )
    except Exception:
        logger.warning('Снимок мониторинга не сохранился', exc_info=True)


def read_snapshot(cache_key: str) -> tuple[dict[str, Any] | None, float | None]:
    """(payload, age_seconds) или (None, None)."""
    if not cache_key:
        return None, None
    try:
        stored = _store().get(cache_key)
    except Exception:
        return None, None
    if not isinstance(stored, dict) or not isinstance(stored.get('payload'), dict):
        return None, None
    if not isinstance(stored['payload'].get('sources'), list):
        return None, None
    try:
        age = timezone.now().timestamp() - float(stored.get('stored_at') or 0)
    except (TypeError, ValueError):
        return None, None
    if age < 0:
        return None, None
    return stored['payload'], age


def _has_metrics(payload: dict[str, Any]) -> bool:
    """У оболочки нет rates: нули в totals — заглушка, не посчитанный снимок."""
    sources = payload.get('sources')
    if not isinstance(sources, list):
        return False
    return any(isinstance(row, dict) and row.get('rates') for row in sources)


def serve_snapshot(
    *,
    cache_key: str,
    shell: Callable[[], dict[str, Any]],
    schedule_rebuild: Callable[[], None] | None = None,
    max_age: int = DEFAULT_MAX_AGE,
    ttl: int = DEFAULT_SNAPSHOT_TTL,
) -> dict[str, Any]:
    """Свежий или устаревший снимок сразу. Без снимка — оболочка. Пересчёт не в GET.

    Оболочку в кэш не кладём: иначе ближайшие запросы отдают нули как свежие числа.
    """
    del ttl
    payload, age = read_snapshot(cache_key)
    if payload is not None and not _has_metrics(payload):
        payload, age = None, None
        try:
            _store().delete(cache_key)
        except Exception:
            logger.warning('Пустая оболочка снимка не снялась', exc_info=True)
    if payload is not None:
        stale = age is None or age > max_age
        if stale and schedule_rebuild is not None:
            try:
                schedule_rebuild()
            except Exception:
                logger.warning('Пересчёт снимка не поставился', exc_info=True)
        result = dict(payload)
        result['stale'] = bool(stale)
        return result
    try:
        payload = shell()
    except Exception:
        logger.exception('Оболочка снимка не собралась')
        payload = {'generated_at': timezone.now().isoformat(), 'sources': [], 'stale': True}
    if schedule_rebuild is not None:
        try:
            schedule_rebuild()
        except Exception:
            logger.warning('Пересчёт снимка не поставился', exc_info=True)
    if isinstance(payload, dict):
        payload = dict(payload)
        payload['stale'] = True
    return payload


def bump_source_status(
    cache_key: str,
    source_id: str,
    status: str,
    *,
    ttl: int = DEFAULT_SNAPSHOT_TTL,
) -> None:
    """Сразу поправить бейдж в кэше после claim/release, не ждать Beat."""
    payload, _age = read_snapshot(cache_key)
    if payload is None:
        return
    store_snapshot(cache_key, patch_status_payload(payload, source_id, status), ttl=ttl)


def shell_sources(
    items: list[dict[str, Any]] | tuple[dict[str, Any], ...],
    *,
    namespace: str,
    status_for,
) -> dict[str, Any]:
    """Короткая оболочка: id, флаги, статус из учёта запуска. Без счетов и рядов."""
    sources = []
    for item in items:
        source_id = str(item.get('id') or '')
        if not source_id:
            continue
        claimed = is_claimed(namespace, source_id)
        row = status_for(item, claimed=claimed)
        sources.append(row)
    return {
        'generated_at': timezone.now().isoformat(),
        'sources': sources,
        'stale': True,
    }
