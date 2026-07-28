"""Ingest и сборка debug-pack для мониторинга клиентов."""

from __future__ import annotations

import logging
import uuid
from collections import Counter
from datetime import timedelta
from typing import Any

from django.conf import settings
from django.db import transaction
from django.utils import timezone
from django.utils.dateparse import parse_datetime

from .models import ClientMonitorEvent, ClientMonitorSession
from .sanitize import sanitize_event, sanitize_session_meta, user_label


logger = logging.getLogger('client.monitor')

IDLE_GAP = timedelta(minutes=5)
AROUND_BEFORE = timedelta(minutes=2)
AROUND_AFTER = timedelta(minutes=1)
MAX_PACK_EVENTS = 800


def _monitoring_enabled() -> bool:
    return bool(getattr(settings, 'CLIENT_MONITORING_ENABLED', False))


def _batch_max() -> int:
    return max(1, int(getattr(settings, 'CLIENT_MONITORING_BATCH_MAX', 100)))


def _file_log_enabled() -> bool:
    return bool(getattr(settings, 'CLIENT_MONITORING_LOG_FILE_ENABLED', True))


def _resolve_session_id(raw: Any) -> uuid.UUID | None:
    if raw is None:
        return None
    try:
        return uuid.UUID(str(raw))
    except (TypeError, ValueError, AttributeError):
        return None


def ingest_events(*, user, session_id, session_meta, events) -> dict[str, Any]:
    """Принять batch событий от авторизованного клиента."""
    if not _monitoring_enabled():
        return {'accepted': 0, 'dropped': 0, 'disabled': True}

    sid = _resolve_session_id(session_id)
    if sid is None:
        return {'accepted': 0, 'dropped': 0, 'error': 'invalid_session_id'}

    if not isinstance(events, list):
        return {'accepted': 0, 'dropped': 0, 'error': 'invalid_events'}

    batch_max = _batch_max()
    dropped = max(0, len(events) - batch_max)
    slice_events = events[:batch_max]

    cleaned: list[dict[str, Any]] = []
    for item in slice_events:
        event = sanitize_event(item)
        if event is None:
            dropped += 1
            continue
        cleaned.append(event)

    if not cleaned and dropped and not session_meta:
        return {'accepted': 0, 'dropped': dropped}

    meta = sanitize_session_meta(session_meta)
    public_id = str(getattr(user, 'public_id', '') or '')
    label = user_label(user)

    with transaction.atomic():
        session, created = ClientMonitorSession.objects.select_for_update().get_or_create(
            public_id=sid,
            defaults={
                'user': user,
                'user_public_id': public_id,
                'user_label': label,
                'user_agent': meta.get('user_agent', ''),
                'language': meta.get('language', ''),
                'timezone': meta.get('timezone', ''),
                'viewport': meta.get('viewport', ''),
                'client_version': meta.get('client_version', ''),
                'scope_claim_keys': meta.get('scope_claim_keys') or [],
            },
        )
        if not created:
            updates: dict[str, Any] = {}
            if session.user_id is None and user is not None:
                updates['user'] = user
            if public_id and session.user_public_id != public_id:
                updates['user_public_id'] = public_id
            if label and session.user_label != label:
                updates['user_label'] = label
            for field in ('user_agent', 'language', 'timezone', 'viewport', 'client_version'):
                value = meta.get(field) or ''
                if value and getattr(session, field) != value:
                    updates[field] = value
            claim_keys = meta.get('scope_claim_keys') or []
            if claim_keys and session.scope_claim_keys != claim_keys:
                updates['scope_claim_keys'] = claim_keys
            if updates:
                for key, value in updates.items():
                    setattr(session, key, value)
                session.save(update_fields=[*updates.keys()])


        existing_seqs = set(
            ClientMonitorEvent.objects.filter(
                session=session,
                seq__in=[e['seq'] for e in cleaned],
            ).values_list('seq', flat=True)
        ) if cleaned else set()

        to_create: list[ClientMonitorEvent] = []
        accepted = 0
        has_error = session.has_errors
        last_at = session.last_event_at
        for event in cleaned:
            if event['seq'] in existing_seqs:
                dropped += 1
                continue
            to_create.append(

                ClientMonitorEvent(
                    session=session,
                    seq=event['seq'],
                    kind=event['kind'],
                    created_at=event['created_at'],
                    payload=event['payload'],
                )
            )
            accepted += 1
            if event['kind'] == ClientMonitorEvent.KIND_ERROR:
                has_error = True
            if last_at is None or event['created_at'] > last_at:
                last_at = event['created_at']

        if to_create:
            ClientMonitorEvent.objects.bulk_create(to_create, ignore_conflicts=True)
            session.event_count = session.event_count + accepted
            session.has_errors = has_error
            session.last_event_at = last_at or timezone.now()
            session.save(update_fields=['event_count', 'has_errors', 'last_event_at'])

    if _file_log_enabled() and accepted:
        logger.info(
            'session=%s user=%s accepted=%s dropped=%s has_errors=%s',
            sid,
            public_id or '-',
            accepted,
            dropped,
            has_error,
        )

    return {
        'accepted': accepted,
        'dropped': dropped,
        'session_id': str(sid),
        'has_errors': has_error,
    }


def split_intervals(events: list[ClientMonitorEvent]) -> list[dict[str, Any]]:
    """Разбить timeline на логические интервалы по паузе ≥ 5 минут."""
    if not events:
        return []
    intervals: list[dict[str, Any]] = []
    current: list[ClientMonitorEvent] = [events[0]]
    for event in events[1:]:
        gap = event.created_at - current[-1].created_at
        if gap >= IDLE_GAP:
            intervals.append(_interval_summary(current, len(intervals)))
            current = [event]
        else:
            current.append(event)
    if current:
        intervals.append(_interval_summary(current, len(intervals)))
    return intervals


def _interval_summary(events: list[ClientMonitorEvent], index: int) -> dict[str, Any]:
    error_count = sum(1 for e in events if e.kind == ClientMonitorEvent.KIND_ERROR)
    return {
        'index': index,
        'from': events[0].created_at.isoformat(),
        'to': events[-1].created_at.isoformat(),
        'event_count': len(events),
        'error_count': error_count,
        'first_seq': events[0].seq,
        'last_seq': events[-1].seq,
    }


def _parse_bound(raw: str | None):
    if not raw:
        return None
    parsed = parse_datetime(raw)
    if parsed is None:
        return None
    if timezone.is_naive(parsed):
        return timezone.make_aware(parsed, timezone.get_current_timezone())
    return parsed


def select_events_for_pack(
    session: ClientMonitorSession,
    *,
    date_from: str | None = None,
    date_to: str | None = None,
    around_error_id: int | None = None,
    interval_index: int | None = None,
) -> list[ClientMonitorEvent]:
    qs = session.events.all().order_by('seq')
    events = list(qs)

    if around_error_id is not None:
        center = next((e for e in events if e.id == around_error_id), None)
        if center is None:
            return []
        start = center.created_at - AROUND_BEFORE
        end = center.created_at + AROUND_AFTER
        return [e for e in events if start <= e.created_at <= end][:MAX_PACK_EVENTS]

    if interval_index is not None:
        intervals = split_intervals(events)
        if interval_index < 0 or interval_index >= len(intervals):
            return []
        info = intervals[interval_index]
        return [
            e for e in events
            if info['first_seq'] <= e.seq <= info['last_seq']
        ][:MAX_PACK_EVENTS]

    start = _parse_bound(date_from)
    end = _parse_bound(date_to)
    if start is not None:
        events = [e for e in events if e.created_at >= start]
    if end is not None:
        events = [e for e in events if e.created_at <= end]
    return events[:MAX_PACK_EVENTS]


def _event_line(event: ClientMonitorEvent) -> str:
    payload = event.payload or {}
    if event.kind == 'nav':
        detail = payload.get('path') or payload.get('to') or payload.get('route_name') or ''
    elif event.kind == 'api':
        method = payload.get('method') or ''
        path = payload.get('path') or payload.get('endpoint') or ''
        status = payload.get('status')
        duration = payload.get('duration_ms')
        parts = [method, path]
        if status is not None:
            parts.append(f'status={status}')
        if duration is not None:
            parts.append(f'{duration}ms')
        detail = ' '.join(str(p) for p in parts if p)
    elif event.kind in {'error', 'warn'}:
        detail = payload.get('message') or ''
        path = payload.get('path') or payload.get('route') or ''
        if path:
            detail = f'{detail} @ {path}'
    else:
        detail = payload.get('message') or payload.get('event') or str(payload)[:120]
    return f'{event.created_at.isoformat()} | {event.kind} | {detail}'.strip()


def build_debug_pack(
    session: ClientMonitorSession,
    events: list[ClientMonitorEvent],
    *,
    mode: str = 'interval',
) -> str:
    """Markdown debug-pack для вставки в Cursor."""
    errors = [e for e in events if e.kind == ClientMonitorEvent.KIND_ERROR]
    api_fail = [
        e for e in events
        if e.kind == ClientMonitorEvent.KIND_API
        and isinstance((e.payload or {}).get('status'), int)
        and int(e.payload['status']) >= 400
    ]
    failing_endpoints = Counter()
    for event in api_fail:
        path = (event.payload or {}).get('path') or (event.payload or {}).get('endpoint') or '?'
        method = (event.payload or {}).get('method') or '?'
        failing_endpoints[f'{method} {path}'] += 1

    first_fail = api_fail[0] if api_fail else None
    interval_from = events[0].created_at.isoformat() if events else ''
    interval_to = events[-1].created_at.isoformat() if events else ''

    lines = [
        '# ERGO MS client debug pack',
        '',
        '## Summary',
        f'- user: {session.user_label or "-"} (`{session.user_public_id or "-"}`)',
        f'- session_id: `{session.public_id}`',
        f'- mode: {mode}',
        f'- interval: {interval_from} → {interval_to}',
        f'- events: {len(events)}',
        f'- error_count: {len(errors)}',
        f'- first_failing_api: {_event_line(first_fail) if first_fail else "-"}',
        '',
        '## Environment',
        f'- user_agent: {session.user_agent or "-"}',
        f'- language: {session.language or "-"}',
        f'- timezone: {session.timezone or "-"}',
        f'- viewport: {session.viewport or "-"}',
        f'- client_version: {session.client_version or "-"}',
        f'- scope_claim_keys: {", ".join(session.scope_claim_keys or []) or "-"}',
        '',
        '## Timeline',
    ]
    if events:
        lines.extend(f'- {_event_line(e)}' for e in events)
    else:
        lines.append('- (empty)')

    lines.extend(['', '## Errors (detail)'])
    if errors:
        for event in errors:
            payload = event.payload or {}
            lines.append(f'### error seq={event.seq} @ {event.created_at.isoformat()}')
            lines.append(f'- message: {payload.get("message") or "-"}')
            lines.append(f'- route: {payload.get("path") or payload.get("route") or "-"}')
            lines.append(f'- component: {payload.get("component") or "-"}')
            stack = payload.get('stack') or ''
            if stack:
                lines.append('- stack:')
                lines.append('```')
                lines.append(str(stack)[:2000])
                lines.append('```')
            lines.append('')
    else:
        lines.append('- none')

    lines.extend(['', '## Hints for fix'])
    if failing_endpoints:
        lines.append('- failing endpoints:')
        for endpoint, count in failing_endpoints.most_common(15):
            lines.append(f'  - {endpoint} × {count}')
    else:
        lines.append('- failing endpoints: none')

    nav_paths = [
        (e.payload or {}).get('path') or (e.payload or {}).get('to')
        for e in events
        if e.kind == ClientMonitorEvent.KIND_NAV
    ]
    nav_paths = [p for p in nav_paths if p]
    if nav_paths:
        repeated = [f'{path} × {count}' for path, count in Counter(nav_paths).most_common(5) if count > 1]
        lines.append(f'- repeated navigation: {", ".join(repeated) if repeated else "none"}')
    else:
        lines.append('- repeated navigation: none')

    status_cluster = Counter()
    for event in api_fail:
        status = (event.payload or {}).get('status')
        if status is not None:
            status_cluster[str(status)] += 1
    if status_cluster:
        cluster = ', '.join(f'{k}×{v}' for k, v in status_cluster.most_common())
        lines.append(f'- http error cluster: {cluster}')
    else:
        lines.append('- http error cluster: none')

    lines.append('')
    lines.append(
        'Используй этот пакет для локализации бага в ERGO MS (Vue client + Django API). '
        'Не предлагай обходы безопасности и не логируй секреты.'
    )
    return '\n'.join(lines)
