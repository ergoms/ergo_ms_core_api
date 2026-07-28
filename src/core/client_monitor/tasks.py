"""Celery-задачи мониторинга клиентов."""

from __future__ import annotations

from celery import shared_task

from .retention import purge_old_client_monitor


@shared_task(name='core.client_monitor.purge_old')
def purge_old_client_monitor_task() -> int:
    """Периодическое удаление по CLIENT_MONITORING_RETENTION_DAYS."""
    return purge_old_client_monitor()
