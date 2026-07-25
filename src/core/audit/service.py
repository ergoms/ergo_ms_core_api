"""Точка входа записи аудита.

Используется внутри ядра и через ModuleBridge (`audit.record`). Инициатор,
IP, User-Agent, измерения (scope) и request_id подхватываются автоматически из
контекста запроса — вызывающему коду достаточно передать `action`.
"""

from __future__ import annotations

import logging
from typing import Any

from django.conf import settings
from django.db import transaction

from .actors import upsert_audit_actor
from .context import resolve_context
from .models import AuditEvent
from .redaction import redact, redact_changes

logger = logging.getLogger('core.audit')

_UNSET = object()

# Поля, допустимые в AuditEvent.objects.create (attname FK — actor_id).
_PERSIST_FIELDS = frozenset({
    'action',
    'source_module',
    'severity',
    'actor_id',
    'actor_label',
    'ip_address',
    'user_agent',
    'request_id',
    'scope',
    'changes',
    'meta',
    'entity_type',
    'entity_ref',
    'entity_label',
})


def _normalize_persist_payload(payload: dict) -> dict:
    """Оставить только поля модели; устаревшие ключи привести к текущей схеме."""
    data = dict(payload or {})
    if 'actor_id' not in data and 'actor_user_id' in data:
        data['actor_id'] = data['actor_user_id']
    data.pop('actor_user_id', None)
    return {key: data[key] for key in _PERSIST_FIELDS if key in data}


def _actor_label(actor) -> str:
    if actor is None:
        return ''
    full_name = ''
    get_full_name = getattr(actor, 'get_full_name', None)
    if callable(get_full_name):
        full_name = (get_full_name() or '').strip()
    username = getattr(actor, 'username', '') or ''
    return full_name or username or str(actor)


def _normalize_entity(entity: Any) -> dict:
    if not isinstance(entity, dict):
        return {}
    return {
        'entity_type': str(entity.get('type') or '')[:64],
        'entity_ref': str(entity.get('ref') or '')[:128],
        'entity_label': str(entity.get('label') or '')[:255],
    }


def log_audit_event(payload: dict) -> None:
    """Строка в logs/audit.log после успешной записи в БД."""
    if not getattr(settings, 'AUDIT_LOG_FILE_ENABLED', True):
        return
    changes = payload.get('changes')
    changes_count = len(changes) if isinstance(changes, list) else 0
    logger.info(
        'action=%s module=%s severity=%s actor=%s entity=%s/%s scope=%s ip=%s request_id=%s changes=%s',
        payload.get('action') or '-',
        payload.get('source_module') or '-',
        payload.get('severity') or '-',
        payload.get('actor_label') or '-',
        payload.get('entity_type') or '-',
        payload.get('entity_ref') or '-',
        payload.get('scope') or '-',
        payload.get('ip_address') or '-',
        payload.get('request_id') or '-',
        changes_count,
    )


def persist_audit_event_sync(payload: dict) -> int:
    """Сохранить запись аудита в БД и продублировать в audit.log."""
    clean = _normalize_persist_payload(payload)
    event = AuditEvent.objects.create(**clean)
    upsert_audit_actor(
        actor_id=clean.get('actor_id'),
        actor_label=clean.get('actor_label') or '',
    )
    log_audit_event(clean)
    return event.pk


class AuditService:
    """Создание записей журнала действий."""

    @staticmethod
    def record(
        *,
        action: str,
        source_module: str = '',
        actor: Any = _UNSET,
        request=None,
        entity: dict | None = None,
        changes: list | None = None,
        meta: dict | None = None,
        severity: str = AuditEvent.SEVERITY_INFO,
        scope: dict | None = None,
    ) -> None:
        """Зафиксировать действие.

        Параметры:
            action (str): ключ действия, например 'user.role_assigned' (обязателен).
            source_module (str): идентификатор источника ('core.cms.adp', 'my_module').
            actor: User; по умолчанию берётся из контекста запроса.
            request: явный request (если контекст недоступен, напр. в Celery).
            entity (dict|None): {'type', 'ref', 'label'} — ref это public_id, не pk.
            changes (list|None): [{'field', 'label', 'old', 'new'}].
            meta (dict|None): произвольные данные (будут очищены от секретов).
            severity (str): info|security|critical.
            scope (dict|None): переопределения измерений журнала (audit.scope_dimensions);
                значение None у ключа удаляет измерение из контекста.

        Ничего не возвращает и никогда не бросает исключение наружу —
        сбой аудита не должен ломать основной запрос.
        """
        try:
            if not action or not isinstance(action, str):
                logger.warning('AuditService.record: пустой action, пропуск')
                return

            ctx = resolve_context(request)

            resolved_actor = ctx['actor'] if actor is _UNSET else actor
            actor_id = getattr(resolved_actor, 'pk', None) if resolved_actor is not None else None

            # Измерения (scope): контекст запроса + переопределения вызывающего кода.
            resolved_scope = dict(ctx.get('scope') or {})
            if scope:
                for key, value in scope.items():
                    if value is None:
                        resolved_scope.pop(key, None)
                    else:
                        resolved_scope[key] = value

            payload = {
                'action': action[:128],
                'source_module': (source_module or '')[:64],
                'severity': severity or AuditEvent.SEVERITY_INFO,
                'actor_id': actor_id,
                'actor_label': _actor_label(resolved_actor),
                'ip_address': ctx['ip_address'],
                'user_agent': ctx['user_agent'],
                'request_id': ctx['request_id'],
                'scope': resolved_scope,
                'changes': redact_changes(changes) if changes else None,
                'meta': redact(meta) if isinstance(meta, dict) else {},
                **_normalize_entity(entity),
            }

            # Пишем только после успешного commit, чтобы не фиксировать
            # действия, которые в итоге откатились.
            if transaction.get_connection().in_atomic_block:
                transaction.on_commit(lambda: AuditService._persist(payload))
            else:
                AuditService._persist(payload)
        except Exception:
            logger.exception('AuditService.record упал для action=%s', action)

    @staticmethod
    def _persist(payload: dict) -> None:
        if getattr(settings, 'AUDIT_ASYNC_PERSIST', False):
            AuditService._enqueue_async(payload)
        else:
            AuditService._persist_sync(payload)

    @staticmethod
    def _enqueue_async(payload: dict) -> None:
        try:
            from .tasks import persist_audit_event

            persist_audit_event.delay(payload)
        except Exception:
            logger.exception('AuditService: не удалось поставить запись аудита в очередь')
            if getattr(settings, 'AUDIT_ASYNC_PERSIST_FALLBACK_SYNC', True):
                AuditService._persist_sync(payload)

    @staticmethod
    def _persist_sync(payload: dict) -> None:
        try:
            persist_audit_event_sync(payload)
        except Exception:
            logger.exception('AuditService: не удалось сохранить запись аудита')
