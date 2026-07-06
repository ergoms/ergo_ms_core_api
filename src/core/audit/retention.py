"""Удаление устаревших записей журнала действий."""

from __future__ import annotations

import logging
from datetime import timedelta

from django.conf import settings
from django.utils import timezone

from .catalog import invalidate_audit_catalog_cache
from .models import AuditEvent

logger = logging.getLogger('core.audit')

DEFAULT_BATCH_SIZE = 1000


def purge_old_audit_events(
    *,
    retention_days: int | None = None,
    batch_size: int = DEFAULT_BATCH_SIZE,
    dry_run: bool = False,
) -> int:
    """Удалить записи старше retention_days. Возвращает число удалённых строк."""
    days = retention_days if retention_days is not None else getattr(settings, 'AUDIT_RETENTION_DAYS', 0)
    if days <= 0:
        logger.info('audit purge: retention отключён (AUDIT_RETENTION_DAYS=%s)', days)
        return 0

    cutoff = timezone.now() - timedelta(days=days)
    batch_size = max(1, batch_size)

    if dry_run:
        count = AuditEvent.objects.filter(created_at__lt=cutoff).count()
        logger.info(
            'audit purge dry-run: %s записей старше %s дней (до %s)',
            count,
            days,
            cutoff.isoformat(),
        )
        return count

    deleted_total = 0
    while True:
        ids = list(
            AuditEvent.objects
            .filter(created_at__lt=cutoff)
            .order_by('id')
            .values_list('id', flat=True)[:batch_size]
        )
        if not ids:
            break
        deleted_count, _ = AuditEvent.objects.filter(id__in=ids).delete()
        deleted_total += deleted_count

    if deleted_total:
        invalidate_audit_catalog_cache()
        logger.info(
            'audit purge: удалено %s записей старше %s дней',
            deleted_total,
            days,
        )
    return deleted_total
