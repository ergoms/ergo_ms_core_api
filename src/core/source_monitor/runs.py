"""Атомарный учёт «источник уже поставлен в очередь».

Опрос Celery — сверка, не источник правды. Пока воркер молчит, запись
остаётся: повторный старт не проходит, бейдж «идёт».
"""

from __future__ import annotations

import logging
import time
from typing import Any

from django.conf import settings
from django.core.cache import caches

logger = logging.getLogger('src.core.source_monitor')

CLAIM_TTL_SECONDS = 6 * 60 * 60
_PREFIX = 'source_run'


def _store():
    if 'live' in settings.CACHES:
        return caches['live']
    return caches['default']


def _run_key(namespace: str, source_id: str) -> str:
    return f'{_PREFIX}:{namespace}:{source_id}'


def _index_key(namespace: str) -> str:
    return f'{_PREFIX}:{namespace}:index'


def _index_add(namespace: str, source_id: str) -> None:
    store = _store()
    key = _index_key(namespace)
    try:
        names = list(store.get(key) or [])
        if source_id not in names:
            names.append(source_id)
            store.set(key, names, CLAIM_TTL_SECONDS)
    except Exception:
        logger.warning('Индекс запусков не записался', exc_info=True)


def _index_remove(namespace: str, source_id: str) -> None:
    store = _store()
    key = _index_key(namespace)
    try:
        names = [name for name in list(store.get(key) or []) if name != source_id]
        if names:
            store.set(key, names, CLAIM_TTL_SECONDS)
        else:
            store.delete(key)
    except Exception:
        logger.warning('Индекс запусков не обновился', exc_info=True)


def claim(namespace: str, source_id: str, *, ttl: int = CLAIM_TTL_SECONDS) -> bool:
    """Занять источник. False — уже занят (или только что занят другим запросом)."""
    if not namespace or not source_id:
        return False
    store = _store()
    payload = {
        'task_ids': [],
        'claimed_at': time.time(),
    }
    try:
        ok = store.add(_run_key(namespace, source_id), payload, max(1, int(ttl)))
    except Exception:
        logger.warning('Захват источника не записался', exc_info=True)
        return False
    if ok:
        _index_add(namespace, source_id)
    return bool(ok)


def attach(
    namespace: str,
    source_id: str,
    task_ids: list[str] | tuple[str, ...] | None,
    *,
    ttl: int = CLAIM_TTL_SECONDS,
) -> None:
    """Дописать id задач, которые реально вернул apply_async."""
    if not namespace or not source_id:
        return
    ids = [str(item) for item in (task_ids or []) if item]
    store = _store()
    key = _run_key(namespace, source_id)
    try:
        current = store.get(key)
        if not isinstance(current, dict):
            current = {'task_ids': [], 'claimed_at': time.time()}
        known = list(current.get('task_ids') or [])
        for task_id in ids:
            if task_id not in known:
                known.append(task_id)
        current['task_ids'] = known
        store.set(key, current, max(1, int(ttl)))
        _index_add(namespace, source_id)
    except Exception:
        logger.warning('Id задач источника не записались', exc_info=True)


def release(namespace: str, source_id: str) -> None:
    if not namespace or not source_id:
        return
    try:
        _store().delete(_run_key(namespace, source_id))
    except Exception:
        logger.warning('Запись запуска не снялась', exc_info=True)
        return
    _index_remove(namespace, source_id)


def is_claimed(namespace: str, source_id: str) -> bool:
    if not namespace or not source_id:
        return False
    try:
        return isinstance(_store().get(_run_key(namespace, source_id)), dict)
    except Exception:
        return False


def task_ids(namespace: str, source_id: str) -> list[str]:
    if not namespace or not source_id:
        return []
    try:
        payload = _store().get(_run_key(namespace, source_id))
    except Exception:
        return []
    if not isinstance(payload, dict):
        return []
    return [str(item) for item in (payload.get('task_ids') or []) if item]


def claimed_ids(namespace: str) -> set[str]:
    if not namespace:
        return set()
    try:
        names = list(_store().get(_index_key(namespace)) or [])
    except Exception:
        return set()
    busy: set[str] = set()
    for name in names:
        source_id = str(name or '')
        if source_id and is_claimed(namespace, source_id):
            busy.add(source_id)
    return busy


def revoke_attached(namespace: str, source_id: str, app) -> int:
    """Отозвать id из записи. Возвращает сколько id отозвали."""
    ids = task_ids(namespace, source_id)
    revoked = 0
    for task_id in ids:
        try:
            app.control.revoke(task_id, terminate=True, signal='SIGTERM')
            revoked += 1
        except Exception:
            logger.warning('Задачу %s не отозвали', task_id, exc_info=True)
    return revoked


_TERMINAL_STATES = frozenset({'SUCCESS', 'FAILURE', 'REVOKED', 'REJECTED'})


def prune_finished(namespace: str, app, inspect_busy: set[str]) -> None:
    """Снять claim, если все прикреплённые задачи уже в терминальном состоянии.

    Вызывать только когда inspect ответил. Задачи ещё в брокере (PENDING)
    или у воркера не трогаем.
    """
    try:
        from celery.result import AsyncResult
    except Exception:
        return
    for source_id in list(claimed_ids(namespace)):
        if source_id in inspect_busy:
            continue
        ids = task_ids(namespace, source_id)
        if not ids:
            continue
        try:
            states = [AsyncResult(task_id, app=app).state for task_id in ids]
        except Exception:
            continue
        if states and all(state in _TERMINAL_STATES for state in states):
            release(namespace, source_id)


def reconcile(
    namespace: str,
    *,
    inspect_busy: set[str] | None,
    alive_task_ids: set[str] | None = None,
    app=None,
) -> set[str]:
    """Свести запись и ответ воркера.

    inspect_busy is None — опрос молчит: все claimed остаются busy.
    Иначе занятость = ответ воркера ∪ claimed. Задачи только в брокере
    не видны в active/reserved; finished claim снимает prune_finished.
    """
    del alive_task_ids
    claimed = claimed_ids(namespace)
    if inspect_busy is None:
        return claimed
    if app is not None:
        prune_finished(namespace, app, inspect_busy)
        claimed = claimed_ids(namespace)
    return set(inspect_busy) | claimed


def patch_status_payload(payload: dict[str, Any], source_id: str, status: str) -> dict[str, Any]:
    """Копия снимка со сменой статуса одной карточки."""
    sources = []
    for row in payload.get('sources') or []:
        if not isinstance(row, dict):
            continue
        item = dict(row)
        if item.get('id') == source_id:
            item['status'] = status
        sources.append(item)
    next_payload = dict(payload)
    next_payload['sources'] = sources
    return next_payload
