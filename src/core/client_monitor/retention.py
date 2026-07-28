"""Удаление устаревших записей мониторинга клиентов."""

from __future__ import annotations

import logging
from datetime import timedelta

from django.conf import settings
from django.utils import timezone

from .models import ClientMonitorSession

logger = logging.getLogger('celery.core.client_monitor')

DEFAULT_BATCH_SIZE = 500


def purge_old_client_monitor(
    *,
    retention_days: int | None = None,
    batch_size: int = DEFAULT_BATCH_SIZE,
    dry_run: bool = False,
) -> int:
    """Удалить сессии (и cascade events) старше retention_days."""
    days = retention_days if retention_days is not None else getattr(
        settings, 'CLIENT_MONITORING_RETENTION_DAYS', 0
    )
    if days <= 0:
        logger.info(
            'client_monitor purge: retention отключён (CLIENT_MONITORING_RETENTION_DAYS=%s)',
            days,
        )
        return 0

    cutoff = timezone.now() - timedelta(days=days)
    batch_size = max(1, batch_size)
    qs = ClientMonitorSession.objects.filter(last_event_at__lt=cutoff)

    if dry_run:
        count = qs.count()
        logger.info(
            'client_monitor purge dry-run: %s сессий старше %s дней (до %s)',
            count,
            days,
            cutoff.isoformat(),
        )
        return count

    deleted_total = 0
    while True:
        ids = list(qs.order_by('id').values_list('id', flat=True)[:batch_size])
        if not ids:
            break
        deleted_count, _ = ClientMonitorSession.objects.filter(id__in=ids).delete()
        deleted_total += deleted_count

    if deleted_total:
        logger.info(
            'client_monitor purge: удалено %s объектов старше %s дней',
            deleted_total,
            days,
        )
    return deleted_total
