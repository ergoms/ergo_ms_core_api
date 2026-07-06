"""Обновление справочника инициаторов для фильтра аудита."""

from __future__ import annotations

import logging
from urllib.parse import quote

from django.contrib.auth import get_user_model

from .models import AuditActor

logger = logging.getLogger('core.audit')

User = get_user_model()


def upsert_audit_actor(*, actor_id: int | None, actor_label: str) -> None:
    """Сохранить или обновить инициатора в dimension-таблице."""
    label = (actor_label or '').strip()
    filter_value = None
    resolved_actor_id = None

    if actor_id:
        row = User.objects.filter(pk=actor_id).values('public_id').first()
        public_id = row.get('public_id') if row else None
        if public_id:
            filter_value = str(public_id)
            resolved_actor_id = actor_id
        elif label:
            filter_value = f'label:{quote(label, safe="")}'
    elif label:
        filter_value = f'label:{quote(label, safe="")}'

    if not filter_value:
        return

    try:
        AuditActor.objects.update_or_create(
            filter_value=filter_value,
            defaults={
                'label': label or filter_value,
                'actor_id': resolved_actor_id,
            },
        )
    except Exception:
        logger.exception('Не удалось обновить AuditActor filter_value=%s', filter_value)
