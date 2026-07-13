"""Celery-задачи журнала действий."""

from __future__ import annotations

import logging

from celery import shared_task

from .retention import purge_old_audit_events
from .service import persist_audit_event_sync

logger = logging.getLogger('celery.core.audit')


@shared_task(name='core.audit.persist', bind=True, max_retries=3, default_retry_delay=30)
def persist_audit_event(self, payload: dict) -> int | None:
    """Асинхронно сохранить запись аудита."""
    try:
        return persist_audit_event_sync(payload)
    except Exception as exc:
        logger.exception(
            'core.audit.persist: ошибка сохранения action=%s',
            payload.get('action'),
        )
        raise self.retry(exc=exc)


@shared_task(name='core.audit.purge_old_events')
def purge_old_events_task() -> int:
    """Периодическое удаление записей по AUDIT_RETENTION_DAYS."""
    return purge_old_audit_events()
