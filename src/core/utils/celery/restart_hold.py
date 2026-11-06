"""Не перезапускать задачи модулей, которые оборвал перезапуск воркера или ergoms.

Брокер с ``task_acks_late`` возвращает недоделанное сообщение в очередь, и после
старта воркер берёт его снова. Здесь перед выполнением ставится метка с номером
жизни воркера. Если сообщение пришло, а метка осталась от прошлой жизни, задачу
оборвали посреди работы. Тогда её не выполняют, а по ``task_restart.yaml`` модуля
откладывают (hold) или выбрасывают (drop). Продолжение — ``ergoms celery-parked
--resume``: задача уходит заново с ``resume=True``, если она его принимает.

Задачи, которые ещё не начинались, идут как обычно.
"""

from __future__ import annotations

import inspect
import logging
import os
import socket
import time
import uuid

from celery.exceptions import Ignore

from src.core.utils.celery.restart_policy import DROP, HOLD, REQUEUE, decide
from src.core.utils.celery.restart_store import get_restart_store

logger = logging.getLogger('celery.restart')

# Новый номер на каждый запуск главного процесса воркера. Дочерние процессы
# prefork получают его при fork, поэтому у всей жизни воркера он один.
WORKER_BOOT_ID = uuid.uuid4().hex
_HOST = socket.gethostname()


def _enabled() -> bool:
    raw = (os.environ.get('CELERY_RESTART_HOLD') or 'on').strip().lower()
    return raw not in {'0', 'off', 'false', 'no'}


def _accepts_kwarg(task, name: str | None) -> bool:
    if not name:
        return False
    try:
        params = inspect.signature(task.run).parameters
    except (TypeError, ValueError):
        return False
    if name in params:
        return True
    return any(p.kind is inspect.Parameter.VAR_KEYWORD for p in params.values())


def _park_record(task, request, decision, previous: dict) -> dict:
    delivery = getattr(request, 'delivery_info', None) or {}
    resume_kwarg = decision.resume_kwarg if _accepts_kwarg(task, decision.resume_kwarg) else None
    return {
        'id': request.id,
        'task': task.name,
        'module': decision.module,
        'args': list(request.args or []),
        'kwargs': dict(request.kwargs or {}),
        'queue': delivery.get('routing_key') or '',
        'resume_kwarg': resume_kwarg,
        'started_at': previous.get('at'),
        'started_host': previous.get('host'),
        'parked_at': time.time(),
        'parked_host': _HOST,
    }


def _interrupted(store, request) -> dict | None:
    previous = store.started(request.id)
    if previous and previous.get('boot') != WORKER_BOOT_ID:
        return previous
    return None


def create_restart_hold_task_class(base_task_class):
    class RestartHoldTask(base_task_class):
        def __call__(self, *args, **kwargs):
            request = self.request
            if not request.id or request.is_eager or not _enabled():
                return super().__call__(*args, **kwargs)
            decision = decide(self.name)
            if decision.action == REQUEUE:
                return super().__call__(*args, **kwargs)
            try:
                store = get_restart_store(self.app)
                previous = _interrupted(store, request)
            except Exception:
                # Хранилище недоступно: лучше выполнить задачу, чем потерять её.
                logger.warning('Метка задачи %s не прочиталась, выполняю', request.id, exc_info=True)
                return super().__call__(*args, **kwargs)
            if previous is not None:
                self._hold_interrupted(store, decision, previous)
            try:
                store.mark_started(
                    request.id,
                    {'boot': WORKER_BOOT_ID, 'host': _HOST, 'at': time.time(), 'task': self.name},
                )
            except Exception:
                logger.debug('Метка задачи %s не записалась', request.id, exc_info=True)
            try:
                return super().__call__(*args, **kwargs)
            finally:
                # Retry, успех и ошибка снимают метку: оборванной считается только
                # задача, которую прервали, не дав дойти сюда.
                try:
                    store.clear_started(request.id)
                except Exception:
                    logger.debug('Метка задачи %s не снялась', request.id, exc_info=True)

        def _hold_interrupted(self, store, decision, previous: dict):
            request = self.request
            if decision.action == HOLD:
                store.park(_park_record(self, request, decision, previous))
                logger.warning(
                    'Задача %s [%s] оборвана перезапуском воркера и отложена. '
                    'Продолжить: ergoms celery-parked --resume %s',
                    self.name,
                    request.id,
                    request.id,
                )
            elif decision.action == DROP:
                logger.warning(
                    'Задача %s [%s] оборвана перезапуском воркера и не запускается снова',
                    self.name,
                    request.id,
                )
            store.clear_started(request.id)
            # Ignore подтверждает сообщение брокеру без выполнения и без статуса FAILURE.
            raise Ignore()

    return RestartHoldTask


def setup_restart_hold(celery_app) -> None:
    """Обернуть базовый класс задач. Вызывать до ограничителя параллелизма:
    тот должен захватить слот раньше, иначе ожидание слота считалось бы стартом."""
    if not _enabled():
        logger.info('Задержка задач после перезапуска выключена (CELERY_RESTART_HOLD=off)')
        return
    celery_app.Task = create_restart_hold_task_class(celery_app.Task)


def parked_tasks(prefix: str = '', app=None) -> list[dict]:
    """Отложенные задачи. prefix — начало имени задачи, например ``modules.<name>.``."""
    try:
        items = get_restart_store(app).parked()
    except Exception:
        logger.debug('Список отложенных задач не прочитался', exc_info=True)
        return []
    return [item for item in items if str(item.get('task') or '').startswith(prefix)]


def auto_restore_allowed(task_name: str) -> bool:
    """Можно ли модулю самому поднимать задачу после обрыва (свои цепочки, сторожа).

    False — по политике модуля задача после перезапуска ждёт человека.
    """
    if not _enabled():
        return True
    return decide(task_name).action == REQUEUE
