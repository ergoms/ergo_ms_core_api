"""Поминутные счётчики и короткое состояние для живых экранов.

Ключи лежат в кэше ``live``, если включён Redis: его видят и API, и воркеры,
в том числе на другом узле. Без Redis остаётся обычный кэш процесса.
Ошибка кэша не должна останавливать вызывающий код.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone as datetime_timezone
from typing import Any

from django.conf import settings
from django.core.cache import caches
from django.utils import timezone

# Неделя на мониторах модулей (вкладка «7 д») плюс сутки запаса. Раньше 48 ч —
# график за неделю обнулялся, хотя карточки в БД оставались.
BUCKET_TTL_SECONDS = 8 * 24 * 60 * 60
STATE_TTL_SECONDS = 120
WATCH_TTL_SECONDS = 30
_PREFIX = 'livemetric'


def _aware(moment: datetime | None) -> datetime:
    current = moment or timezone.now()
    if timezone.is_naive(current):
        return timezone.make_aware(current, timezone.get_current_timezone())
    return current


def _minute(moment: datetime) -> datetime:
    return moment.replace(second=0, microsecond=0)


def _stamp(moment: datetime) -> str:
    return moment.astimezone(datetime_timezone.utc).strftime('%Y%m%d%H%M')


def _bucket_key(namespace: str, metric: str, moment: datetime) -> str:
    return f'{_PREFIX}:{namespace}:{metric}:{_stamp(moment)}'


def _state_key(namespace: str, source: str) -> str:
    return f'{_PREFIX}:{namespace}:state:{source}'


def _index_key(namespace: str) -> str:
    return f'{_PREFIX}:{namespace}:sources'


def _watch_key(namespace: str) -> str:
    return f'{_PREFIX}:{namespace}:watched'


def _store():
    if 'live' in settings.CACHES:
        return caches['live']
    return caches['default']


def incr(namespace: str, metric: str, n: int = 1, *, now: datetime | None = None) -> None:
    """Прибавить n к бакету текущей минуты. Ключ живёт BUCKET_TTL_SECONDS."""
    amount = int(n)
    if amount <= 0 or not namespace or not metric:
        return
    key = _bucket_key(namespace, metric, _minute(_aware(now)))
    store = _store()
    try:
        store.incr(key, amount)
    except ValueError:
        if not store.add(key, amount, BUCKET_TTL_SECONDS):
            try:
                store.incr(key, amount)
            except ValueError:
                store.set(key, amount, BUCKET_TTL_SECONDS)
        return
    except Exception:
        return
    try:
        store.touch(key, BUCKET_TTL_SECONDS)
    except Exception:
        return


def _minutes(count: int, *, now: datetime | None = None) -> list[datetime]:
    end = _minute(_aware(now))
    width = max(1, int(count))
    start = end - timedelta(minutes=width - 1)
    return [start + timedelta(minutes=offset) for offset in range(width)]


def series(
    namespace: str,
    metrics: list[str],
    minutes: int,
    *,
    now: datetime | None = None,
) -> list[dict[str, Any]]:
    """Поминутный ряд. Нет бакета — ноль. Точки идут от старых к новым."""
    slots = _minutes(minutes, now=now)
    names = [name for name in metrics if name]
    keys = [_bucket_key(namespace, name, slot) for slot in slots for name in names]
    try:
        found = _store().get_many(keys) if keys else {}
    except Exception:
        found = {}
    rows: list[dict[str, Any]] = []
    for slot in slots:
        row: dict[str, Any] = {'t': slot.isoformat()}
        for name in names:
            raw = found.get(_bucket_key(namespace, name, slot), 0)
            try:
                row[name] = int(raw or 0)
            except (TypeError, ValueError):
                row[name] = 0
        rows.append(row)
    return rows


def hourly(
    namespace: str,
    metrics: list[str],
    hours: int,
    *,
    now: datetime | None = None,
) -> list[dict[str, Any]]:
    """Тот же ряд, сложенный по часам."""
    points = series(namespace, metrics, max(1, int(hours)) * 60, now=now)
    names = [name for name in metrics if name]
    buckets: dict[str, dict[str, Any]] = {}
    order: list[str] = []
    for point in points:
        hour = str(point['t'])[:13]
        row = buckets.get(hour)
        if row is None:
            row = {'t': f'{hour}:00:00'}
            for name in names:
                row[name] = 0
            buckets[hour] = row
            order.append(hour)
        for name in names:
            row[name] += int(point.get(name) or 0)
    return [buckets[hour] for hour in order]


def put_state(
    namespace: str,
    source: str,
    payload: dict[str, Any],
    ttl: int = STATE_TTL_SECONDS,
) -> None:
    """Последнее состояние источника. Пока ключ жив, источник считается свежим."""
    if not namespace or not source:
        return
    store = _store()
    try:
        store.set(_state_key(namespace, source), payload, max(1, int(ttl)))
        index = _index_key(namespace)
        names = list(store.get(index) or [])
        if source not in names:
            names.append(source)
            store.set(index, names, BUCKET_TTL_SECONDS)
    except Exception:
        return


def get_states(namespace: str) -> dict[str, dict[str, Any]]:
    try:
        store = _store()
        names = list(store.get(_index_key(namespace)) or [])
    except Exception:
        return {}
    states: dict[str, dict[str, Any]] = {}
    for name in names:
        try:
            payload = store.get(_state_key(namespace, name))
        except Exception:
            continue
        if isinstance(payload, dict):
            states[str(name)] = payload
    return states


def mark_watched(namespace: str, ttl: int = WATCH_TTL_SECONDS) -> None:
    """Страницу кто-то открыл. Пока отметка жива, снимок имеет смысл рассылать."""
    if not namespace:
        return
    try:
        _store().set(_watch_key(namespace), 1, max(1, int(ttl)))
    except Exception:
        return


def is_watched(namespace: str) -> bool:
    if not namespace:
        return False
    try:
        return bool(_store().get(_watch_key(namespace)))
    except Exception:
        return False
