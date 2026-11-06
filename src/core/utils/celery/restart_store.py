"""Метки начатых задач и отложенные задачи после перезапуска.

При брокере Redis всё лежит в нём же: метку ставит один узел кластера, а
читает другой. Для брокера в БД или SQLite — файлы в virtual_env/cache.
"""

from __future__ import annotations

import json
import logging
import os
import time
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator

logger = logging.getLogger('celery.restart')

STARTED_PREFIX = 'ergo:celery:restart:started:'
PARKED_KEY = 'ergo:celery:restart:parked'
# Метка живёт дольше visibility_timeout брокера (4 суток): задача может идти сутками.
STARTED_TTL_SEC = 30 * 24 * 3600


def _dumps(value: dict) -> str:
    return json.dumps(value, ensure_ascii=False, default=str)


def _loads(raw) -> dict | None:
    if raw is None:
        return None
    if isinstance(raw, bytes):
        raw = raw.decode('utf-8', errors='replace')
    try:
        value = json.loads(raw)
    except (TypeError, ValueError):
        return None
    return value if isinstance(value, dict) else None


class RedisRestartStore:
    def __init__(self, app) -> None:
        self._app = app

    @contextmanager
    def _client(self) -> Iterator:
        with self._app.pool.acquire(block=True, timeout=5) as conn:
            yield conn.default_channel.client

    def mark_started(self, task_id: str, payload: dict) -> None:
        with self._client() as client:
            client.set(STARTED_PREFIX + task_id, _dumps(payload), ex=STARTED_TTL_SEC)

    def started(self, task_id: str) -> dict | None:
        with self._client() as client:
            return _loads(client.get(STARTED_PREFIX + task_id))

    def clear_started(self, task_id: str) -> None:
        with self._client() as client:
            client.delete(STARTED_PREFIX + task_id)

    def park(self, record: dict) -> None:
        with self._client() as client:
            client.hset(PARKED_KEY, record['id'], _dumps(record))

    def parked(self) -> list[dict]:
        with self._client() as client:
            raw = client.hgetall(PARKED_KEY) or {}
        items = [_loads(value) for value in raw.values()]
        return [item for item in items if item]

    def unpark(self, parked_id: str) -> dict | None:
        """Забрать запись. Два одновременных --resume не поставят задачу дважды."""
        with self._client() as client:
            pipe = client.pipeline()
            pipe.hget(PARKED_KEY, parked_id)
            pipe.hdel(PARKED_KEY, parked_id)
            raw, removed = pipe.execute()
        return _loads(raw) if removed else None


class FileRestartStore:
    def __init__(self, root: Path) -> None:
        self._started = root / 'started'
        self._parked = root / 'parked'

    @staticmethod
    def _safe(name: str) -> str:
        return ''.join(ch for ch in str(name) if ch.isalnum() or ch in '-_')

    @staticmethod
    def _write(path: Path, payload: dict) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(f'.{os.getpid()}.tmp')
        tmp.write_text(_dumps(payload), encoding='utf-8')
        os.replace(tmp, path)

    @staticmethod
    def _read(path: Path) -> dict | None:
        try:
            return _loads(path.read_text(encoding='utf-8'))
        except OSError:
            return None

    def mark_started(self, task_id: str, payload: dict) -> None:
        self._write(self._started / f'{self._safe(task_id)}.json', payload)

    def started(self, task_id: str) -> dict | None:
        path = self._started / f'{self._safe(task_id)}.json'
        try:
            if time.time() - path.stat().st_mtime > STARTED_TTL_SEC:
                path.unlink(missing_ok=True)
                return None
        except OSError:
            return None
        return self._read(path)

    def clear_started(self, task_id: str) -> None:
        (self._started / f'{self._safe(task_id)}.json').unlink(missing_ok=True)

    def park(self, record: dict) -> None:
        self._write(self._parked / f'{self._safe(record["id"])}.json', record)

    def parked(self) -> list[dict]:
        if not self._parked.is_dir():
            return []
        items = [self._read(path) for path in sorted(self._parked.glob('*.json'))]
        return [item for item in items if item]

    def unpark(self, parked_id: str) -> dict | None:
        path = self._parked / f'{self._safe(parked_id)}.json'
        claimed = path.with_suffix(f'.{os.getpid()}.claim')
        try:
            # rename атомарен: второй --resume получит FileNotFoundError.
            os.replace(path, claimed)
        except OSError:
            return None
        record = self._read(claimed)
        claimed.unlink(missing_ok=True)
        return record


def _uses_redis(app) -> bool:
    url = str(app.conf.broker_url or '')
    return url.startswith('redis://') or url.startswith('rediss://')


def get_restart_store(app=None):
    if app is None:
        from src.config.celery import celery_app as app
    if _uses_redis(app):
        return RedisRestartStore(app)
    from src.config.paths import CACHE_DIR

    return FileRestartStore(CACHE_DIR / 'celery_restart')
