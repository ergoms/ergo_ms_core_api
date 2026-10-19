"""Перечитывает decision.json и обновляет лимиты очередей без рестарта воркера."""

from __future__ import annotations

import json
import logging
import os
import sys
import threading
from pathlib import Path
from typing import Any

from src.config.paths import CACHE_DIR
from src.core.utils.celery.concurrency import queue_concurrency_manager

logger = logging.getLogger('celery.concurrency')

_DECISION = CACHE_DIR / 'celery_balance' / 'decision.json'
_watcher_started = False
_watcher_lock = threading.Lock()
_overlay_paused: set[str] = set()
_consumers_released: set[str] = set()
_live_nodename = ''
_nodename_hooked = False
_CLUSTER_ON = {'on', '1', 'true', 'yes'}


def _argv_queues() -> set[str]:
    """Очереди из -Q этого процесса. Чужие паузы сюда не подписываем."""
    argv = sys.argv
    raw = ''
    for index, arg in enumerate(argv):
        if arg.startswith('--queues='):
            raw = arg.split('=', 1)[1]
            break
        if arg == '-Q' or arg == '--queues':
            if index + 1 < len(argv):
                raw = argv[index + 1]
            break
        if arg.startswith('-Q') and len(arg) > 2:
            raw = arg[2:]
            break
    return {part.strip() for part in raw.split(',') if part.strip()}


def _worker_hostname() -> str:
    argv = sys.argv
    for index, arg in enumerate(argv):
        if arg.startswith('--hostname='):
            return arg.split('=', 1)[1].strip()
        if arg == '--hostname' and index + 1 < len(argv):
            return argv[index + 1].strip()
    return ''


def _project_env() -> dict[str, str]:
    """Файлы env проекта. У воркера модуля флага кластера в начальном окружении процесса нет."""
    try:
        import sys

        from src.config.paths import DEPLOYMENT_DIR, SYSTEM_DIR

        deployment = str(DEPLOYMENT_DIR)
        if deployment not in sys.path:
            sys.path.insert(0, deployment)
        from env_file_loader import load_project_env

        loaded = load_project_env(SYSTEM_DIR)
    except Exception:
        return {}
    return loaded if isinstance(loaded, dict) else {}


def _setting(name: str) -> str:
    current = os.environ.get(name, '').strip()
    if current:
        return current
    return str(_project_env().get(name) or '').strip()


def _cluster_enabled() -> bool:
    return _setting('CELERY_CLUSTER').lower() in _CLUSTER_ON


def _remember_nodename(sender: str | None = None, **_kwargs: Any) -> None:
    global _live_nodename
    if sender:
        _live_nodename = str(sender)


def _ensure_nodename_hook() -> None:
    global _nodename_hooked
    if _nodename_hooked:
        return
    try:
        from celery.signals import celeryd_init
    except Exception:
        return
    celeryd_init.connect(_remember_nodename, weak=False)
    _nodename_hooked = True


def _control_destination() -> str:
    """Имя, под которым воркер слушает команды. Без @ Celery сам ставит префикс celery@."""
    if _live_nodename:
        return _live_nodename
    raw = _worker_hostname()
    if not raw:
        return ''
    try:
        from celery.utils.nodenames import default_nodename

        return default_nodename(raw)
    except Exception:
        return raw if '@' in raw else f'celery@{raw}'


def _sync_paused_consumers(paused: set[str]) -> None:
    """Пауза семафором не отписывает consumer: сообщения всё равно забирает этот узел."""
    global _consumers_released
    if not _cluster_enabled():
        return
    hostname = _control_destination()
    mine = _argv_queues()
    if not hostname or not mine:
        return
    target = paused & mine
    release = target - _consumers_released
    restore = (_consumers_released & mine) - paused
    if not release and not restore:
        return
    try:
        from celery import current_app
    except Exception:
        return
    failed = False
    for name in sorted(release):
        try:
            current_app.control.cancel_consumer(name, destination=[hostname])
        except Exception:
            logger.debug('Не удалось снять consumer %s', name, exc_info=True)
            failed = True
    for name in sorted(restore):
        try:
            current_app.control.add_consumer(name, destination=[hostname])
        except Exception:
            logger.debug('Не удалось вернуть consumer %s', name, exc_info=True)
            failed = True
    if not failed:
        _consumers_released = set(target)


def _load_decision(path: Path) -> dict[str, Any] | None:
    if not path.is_file():
        return None
    try:
        data = json.loads(path.read_text(encoding='utf-8'))
    except (OSError, json.JSONDecodeError):
        return None
    return data if isinstance(data, dict) else None


def apply_decision_limits(data: dict[str, Any] | None) -> None:
    """Накладывает queue_limits, pause_queues и non_light_cap из overlay."""
    global _overlay_paused
    if not data:
        return
    raw_limits = data.get('queue_limits')
    limits: dict[str, int] = {}
    if isinstance(raw_limits, dict):
        for name, value in raw_limits.items():
            try:
                parsed = int(value)
            except (TypeError, ValueError):
                continue
            limits[str(name)] = parsed
    raw_pause = data.get('pause_queues')
    paused = {
        str(item)
        for item in (raw_pause if isinstance(raw_pause, list) else [])
        if str(item).strip()
    }

    for queue_name in list(_overlay_paused - paused):
        queue_concurrency_manager.set_paused(queue_name, False)
    for queue_name in paused:
        queue_concurrency_manager.set_paused(queue_name, True)
    _overlay_paused = set(paused)

    for queue_name, overlay_limit in limits.items():
        if queue_name in paused:
            continue
        if overlay_limit <= 0:
            continue
        current = queue_concurrency_manager.get_queue_limit(queue_name)
        effective = overlay_limit if current <= 0 else min(current, overlay_limit)
        queue_concurrency_manager.update_queue_limit(queue_name, effective)

    raw_classes = data.get('queue_classes')
    classes: dict[str, str] = {}
    if isinstance(raw_classes, dict):
        classes = {
            str(name): str(task_class)
            for name, task_class in raw_classes.items()
            if str(name).strip() and str(task_class).strip()
        }
    else:
        plans = data.get('plans')
        if isinstance(plans, dict):
            for raw_plan in plans.values():
                if not isinstance(raw_plan, dict):
                    continue
                plan_classes = raw_plan.get('queue_classes')
                if isinstance(plan_classes, dict):
                    classes.update(
                        {
                            str(name): str(task_class)
                            for name, task_class in plan_classes.items()
                            if str(name).strip() and str(task_class).strip()
                        }
                    )
    queue_concurrency_manager.set_queue_classes(classes)

    non_light_cap = 0
    raw_cap = data.get('non_light_cap')
    try:
        non_light_cap = int(raw_cap) if raw_cap is not None else 0
    except (TypeError, ValueError):
        non_light_cap = 0
    if non_light_cap <= 0:
        plans = data.get('plans')
        if isinstance(plans, dict):
            caps = []
            for raw_plan in plans.values():
                if not isinstance(raw_plan, dict):
                    continue
                try:
                    parsed = int(raw_plan.get('non_light_cap') or 0)
                except (TypeError, ValueError):
                    parsed = 0
                if parsed > 0:
                    caps.append(parsed)
            if caps:
                non_light_cap = min(caps)
    queue_concurrency_manager.set_non_light_cap(max(0, non_light_cap))
    _sync_paused_consumers(paused)


def _load_cluster_plan() -> dict[str, Any] | None:
    """План этого узла из Redis. Нет ключа или брокер молчит — None, дальше файл."""
    import socket

    flag = _setting('CELERY_CLUSTER').lower()
    if flag not in _CLUSTER_ON:
        return None
    node_id = _setting('ERGO_NODE_ID') or socket.gethostname()
    url = _setting('CELERY_BROKER_URL')
    if not url:
        try:
            from django.conf import settings

            url = str(getattr(settings, 'CELERY_BROKER_URL', '') or '')
        except Exception:
            url = ''
    if not url.startswith('redis'):
        return None
    try:
        import redis
    except ImportError:
        return None
    try:
        client = redis.Redis.from_url(url, socket_timeout=1.5, decode_responses=True)
        raw = client.get(f'celery_balance:plan:{node_id}')
    except Exception:
        logger.debug('План узла из Redis недоступен', exc_info=True)
        return None
    if not raw:
        return None
    try:
        data = json.loads(raw)
    except (TypeError, json.JSONDecodeError):
        return None
    return data if isinstance(data, dict) else None


def reload_overlay_limits(path: Path | None = None) -> bool:
    data = _load_cluster_plan() or _load_decision(path or _DECISION)
    if data is None:
        return False
    apply_decision_limits(data)
    return True


def start_overlay_limit_watcher(*, interval_sec: float = 30.0) -> None:
    global _watcher_started
    with _watcher_lock:
        if _watcher_started:
            return
        _watcher_started = True

    _ensure_nodename_hook()
    reload_overlay_limits()

    def _loop() -> None:
        while True:
            try:
                reload_overlay_limits()
            except Exception:
                logger.debug('Не удалось обновить лимиты очередей из overlay', exc_info=True)
            threading.Event().wait(max(5.0, float(interval_sec)))

    thread = threading.Thread(
        target=_loop,
        name='celery-balance-overlay-limits',
        daemon=True,
    )
    thread.start()
