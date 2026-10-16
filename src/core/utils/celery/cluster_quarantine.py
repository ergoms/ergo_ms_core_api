"""Карантин очереди, которой на рабочем узле не хватило локального ресурса.

Срабатывает только при CELERY_CLUSTER_ROLE=agent. Ключ в Redis читает
планировщик и оставляет очередь на основном сервере.
"""

from __future__ import annotations

import json
import logging
import os
import socket
from datetime import datetime, timezone

logger = logging.getLogger('celery.concurrency')

QUARANTINE_PREFIX = 'celery_balance:quarantine:'
REQUEUE_HEADER = 'ergo_cluster_requeue'
MAX_REQUEUE = 3
_LOOPBACK = ('127.0.0.1', 'localhost', '::1')
_CONNECT_NAMES = frozenset({
    'ConnectionError',
    'ConnectTimeout',
    'NewConnectionError',
    'MaxRetryError',
    'URLError',
})
_REFUSED_ERRNO = frozenset({111, 61, 10061})


class RequiresPrimaryNode(Exception):
    """Модуль явно говорит, что задача должна идти на основном сервере."""


def _chain(exc: BaseException):
    seen: set[int] = set()
    current: BaseException | None = exc
    while current is not None and id(current) not in seen and len(seen) < 6:
        seen.add(id(current))
        yield current
        current = current.__cause__ or current.__context__


def _looks_like_connect(exc: BaseException) -> bool:
    if isinstance(exc, (ConnectionError, TimeoutError, ConnectionRefusedError)):
        return True
    errno = getattr(exc, 'errno', None)
    if errno in _REFUSED_ERRNO:
        return True
    return type(exc).__name__ in _CONNECT_NAMES


def _mentions_loopback(exc: BaseException) -> bool:
    parts = [str(exc)]
    args = getattr(exc, 'args', ())
    if isinstance(args, tuple):
        parts.extend(str(item) for item in args)
    blob = ' '.join(parts)
    return any(token in blob for token in _LOOPBACK)


def is_local_resource_error(exc: BaseException | None) -> bool:
    if exc is None:
        return False
    for item in _chain(exc):
        if isinstance(item, (RequiresPrimaryNode, FileNotFoundError, NotADirectoryError, ModuleNotFoundError)):
            return True
        if _looks_like_connect(item) and _mentions_loopback(item):
            return True
    return False


def requeue_count(headers: dict | None) -> int:
    if not isinstance(headers, dict):
        return 0
    try:
        return max(0, int(headers.get(REQUEUE_HEADER) or 0))
    except (TypeError, ValueError):
        return 0


def should_requeue(headers: dict | None) -> bool:
    return requeue_count(headers) < MAX_REQUEUE


def next_requeue_headers(headers: dict | None) -> dict:
    merged = dict(headers or {})
    merged[REQUEUE_HEADER] = requeue_count(headers) + 1
    return merged


def _countdown() -> float:
    raw = os.environ.get('CELERY_BALANCE_WATCH_INTERVAL', '').strip()
    try:
        interval = float(raw) if raw else 30.0
    except ValueError:
        interval = 30.0
    if interval < 5.0:
        interval = 5.0
    return interval + 5.0


def _queue_name(task) -> str:
    request = getattr(task, 'request', None)
    delivery = getattr(request, 'delivery_info', None) or {}
    for key in ('routing_key', 'exchange'):
        value = delivery.get(key)
        if value:
            return str(value)
    queue = getattr(request, 'queue', None)
    if queue:
        return str(queue)
    return ''


def _request_headers(task) -> dict:
    request = getattr(task, 'request', None)
    headers = getattr(request, 'headers', None)
    return dict(headers) if isinstance(headers, dict) else {}


def _broker_url() -> str:
    url = os.environ.get('CELERY_BROKER_URL', '').strip()
    if url:
        return url
    try:
        from django.conf import settings

        return str(getattr(settings, 'CELERY_BROKER_URL', '') or '')
    except Exception:
        return ''


def _ttl() -> int:
    raw = os.environ.get('CELERY_CLUSTER_QUARANTINE_TTL', '').strip()
    try:
        ttl = int(raw) if raw else 7 * 24 * 3600
    except ValueError:
        ttl = 7 * 24 * 3600
    return ttl if ttl >= 60 else 7 * 24 * 3600


def publish_quarantine(queue: str, reason: str) -> bool:
    url = _broker_url()
    if not queue or not url.startswith('redis'):
        return False
    try:
        import redis
    except ImportError:
        return False
    payload = {
        'queue': queue,
        'reason': reason,
        'node_id': os.environ.get('ERGO_NODE_ID', '').strip() or socket.gethostname(),
        'ts': datetime.now(timezone.utc).isoformat(),
    }
    try:
        client = redis.Redis.from_url(url, socket_timeout=1.5, decode_responses=True)
        client.set(f'{QUARANTINE_PREFIX}{queue}', json.dumps(payload, ensure_ascii=False), ex=_ttl())
    except Exception:
        logger.debug('Не удалось записать карантин очереди %s', queue, exc_info=True)
        return False
    return True


def on_task_failure(sender=None, exception=None, args=None, kwargs=None, **_extra) -> None:
    if os.environ.get('CELERY_CLUSTER_ROLE', '').strip().lower() != 'agent':
        return
    if sender is None or not is_local_resource_error(exception):
        return
    headers = _request_headers(sender)
    if not should_requeue(headers):
        return
    queue = _queue_name(sender)
    if not queue:
        return
    reason = type(exception).__name__ if exception is not None else 'error'
    try:
        from src.core.utils.celery.concurrency import queue_concurrency_manager

        queue_concurrency_manager.set_paused(queue, True)
    except Exception:
        logger.debug('Не удалось поставить очередь %s на паузу', queue, exc_info=True)
    publish_quarantine(queue, reason)
    try:
        sender.apply_async(
            args=args or (),
            kwargs=kwargs or {},
            queue=queue,
            countdown=_countdown(),
            headers=next_requeue_headers(headers),
        )
    except Exception:
        logger.debug('Не удалось переотправить задачу очереди %s', queue, exc_info=True)


def connect_quarantine() -> None:
    if os.environ.get('CELERY_CLUSTER_ROLE', '').strip().lower() != 'agent':
        return
    from celery.signals import task_failure

    task_failure.connect(on_task_failure, weak=False)
