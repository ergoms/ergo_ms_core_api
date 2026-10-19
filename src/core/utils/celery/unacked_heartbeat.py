"""Пульс незакрытых задач. Мёртвый воркер перестаёт его писать, и задачу можно вернуть."""

from __future__ import annotations

import logging
import sys
import threading
import time

from celery import bootsteps

logger = logging.getLogger('celery.worker')


def _contract() -> tuple[str, float] | None:
    try:
        from src.config.paths import DEPLOYMENT_DIR
    except Exception:
        return None
    deployment = str(DEPLOYMENT_DIR)
    if deployment not in sys.path:
        sys.path.insert(0, deployment)
    try:
        from celery_requeue.decide import HEARTBEAT_INTERVAL_SEC, HEARTBEAT_KEY
    except Exception:
        logger.debug('unacked heartbeat contract is unavailable', exc_info=True)
        return None
    return HEARTBEAT_KEY, float(HEARTBEAT_INTERVAL_SEC)


class UnackedHeartbeat(bootsteps.StartStopStep):
    """Пишет в Redis метку времени по каждому ещё не подтверждённому delivery tag."""

    requires = {'celery.worker.consumer.tasks:Tasks'}

    def __init__(self, consumer, **kwargs):
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self._tags: set[str] = set()
        super().__init__(consumer, **kwargs)

    def start(self, consumer):
        transport = getattr(getattr(consumer, 'connection', None), 'transport', None)
        if getattr(transport, 'driver_type', '') != 'redis':
            return
        contract = _contract()
        if contract is None:
            return
        self._key, interval = contract
        self._consumer = consumer
        self._stop.clear()
        self._thread = threading.Thread(
            target=self._loop,
            args=(interval,),
            name='unacked-heartbeat',
            daemon=True,
        )
        self._thread.start()

    def stop(self, consumer):
        self._stop.set()

    def _loop(self, interval: float) -> None:
        while not self._stop.is_set():
            try:
                self._tick()
            except Exception:
                logger.debug('unacked heartbeat tick failed', exc_info=True)
            if self._stop.wait(interval):
                return

    def _tick(self) -> None:
        consumer = self._consumer
        task_consumer = getattr(consumer, 'task_consumer', None)
        channel = getattr(task_consumer, 'channel', None)
        qos = getattr(channel, 'qos', None)
        delivered = getattr(qos, '_delivered', None)
        if channel is None or delivered is None or not hasattr(channel, 'conn_or_acquire'):
            return
        tags = {str(tag) for tag in list(delivered.keys())}
        gone = self._tags - tags
        with channel.conn_or_acquire() as client:
            pipe = client.pipeline()
            for tag in tags:
                pipe.hset(self._key, tag, str(int(time.time())))
            if gone:
                pipe.hdel(self._key, *gone)
            if tags or gone:
                pipe.execute()
        self._tags = tags


def register_unacked_heartbeat(app) -> None:
    app.steps['consumer'].add(UnackedHeartbeat)
