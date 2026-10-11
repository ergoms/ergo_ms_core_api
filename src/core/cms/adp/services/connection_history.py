"""Scoped connection history. Identity and scope are resolved from validated requests."""
from __future__ import annotations

import hashlib
import json
from ipaddress import ip_address
from datetime import timedelta
from uuid import UUID

from django.db import transaction
from django.db.models import Exists, Max, OuterRef, Q
from django.utils import timezone

from src.core.integrations import bridge
from src.core.integrations.module_contracts import SESSION_CONNECTION_SCOPES
from src.core.cms.adp.models import PresenceConnection, SessionConnectionInterval, UserDevice
from src.core.cms.adp.services.presence import get_presence_stale_threshold_seconds
from src.core.cms.adp.services.session_devices import get_request_device_id, touch_device_activity
from src.core.cms.adp.user_agent_utils import get_client_ip, parse_user_agent

RETENTION_DAYS = 90
END_REASONS = frozenset({'disconnect', 'scope_changed', 'logout', 'revoked', 'expired'})


def parse_connection_id(raw):
    if raw in (None, ''):
        return None
    try:
        return UUID(str(raw))
    except (ValueError, TypeError, AttributeError) as exc:
        raise ValueError('Invalid connection_id') from exc


def scope_hash(scope):
    return hashlib.sha256(json.dumps(scope, sort_keys=True, separators=(',', ':')).encode()).hexdigest()


def request_scopes(request):
    auth = getattr(request.auth, 'payload', request.auth)
    responses = bridge.emit(
        SESSION_CONNECTION_SCOPES, user_public_id=str(request.user.public_id), claims=dict(auth),
    )
    # Remote descriptors have no callable resolver; the event carries JSON only.
    scopes = [
        {str(key): value} for response in responses if isinstance(response, dict)
        for key, value in response.items() if value not in (None, '') and isinstance(value, (str, int))
    ]
    return scopes


def cutoff(now):
    return now - timedelta(seconds=get_presence_stale_threshold_seconds())


def _fresh(interval, now):
    return interval.connections.filter(is_active=True, last_seen__gt=cutoff(now)).exists()


def _finish(interval, *, now, reason, ended_at=None):
    interval.closed_at = now
    interval.ended_at = ended_at
    interval.end_reason = reason
    interval.save(update_fields=['closed_at', 'ended_at', 'end_reason'])
    interval.connections.update(is_active=False)


def _expire(interval, now):
    if interval.closed_at is None and not _fresh(interval, now):
        _finish(interval, now=now, reason='timeout')


@transaction.atomic
def heartbeat(request, connection_id, *, now=None):
    """A shared device row serializes concurrent tabs and revocations."""
    connection_id = parse_connection_id(connection_id)
    if connection_id is None:
        return
    now = now or timezone.now()
    device = UserDevice.objects.select_for_update().filter(
        pk=get_request_device_id(request), user=request.user, is_active=True,
    ).first()
    if device is None:
        return
    touch_device_activity(request)
    scopes = request_scopes(request)
    if not scopes:
        return
    # A terminal tab ID cannot be resurrected by a late request after logout/scope switch.
    if PresenceConnection.objects.filter(
        connection_id=connection_id, user=request.user, device_key=device.pk, is_terminal=True,
    ).exists():
        return
    parsed = parse_user_agent(request.META.get('HTTP_USER_AGENT', '') or device.user_agent)
    ip = get_client_ip(request) or device.ip_address
    try:
        ip = str(ip_address(ip))
    except ValueError:
        ip = str(device.ip_address)
    for scope in scopes:
        digest = scope_hash(scope)
        interval = SessionConnectionInterval.objects.select_for_update().filter(
            user=request.user, device_key=device.pk, scope_hash=digest, closed_at__isnull=True,
        ).first()
        if interval is not None:
            # Only this lease can keep the interval alive; stale intervals start afresh.
            _expire(interval, now)
            if interval.closed_at is not None:
                interval = None
        if interval is None:
            interval = SessionConnectionInterval.objects.select_for_update().filter(
                user=request.user, device_key=device.pk, scope_hash=digest,
                end_reason='disconnect', last_seen__gt=cutoff(now),
            ).order_by('-started_at').first()
            if interval is not None:
                interval.closed_at = interval.ended_at = None
                interval.end_reason = ''
                interval.save(update_fields=['closed_at', 'ended_at', 'end_reason'])
        if interval is None:
            interval = SessionConnectionInterval.objects.create(
                user=request.user, device_key=device.pk, scope=scope, scope_hash=digest,
                device_name=device.device_name, device_type=device.device_type,
                browser=parsed['browser'], os=parsed['os'], ip_address=ip,
                started_at=now, last_seen=now,
            )
        PresenceConnection.objects.update_or_create(
            connection_id=connection_id, user=request.user, device_key=device.pk, scope_hash=digest,
            defaults={'interval': interval, 'last_seen': now, 'is_active': True, 'is_terminal': False},
        )
        interval.last_seen = now
        interval.save(update_fields=['last_seen'])


@transaction.atomic
def disconnect(request, connection_id, *, reason='disconnect', terminal=None, now=None):
    connection_id = parse_connection_id(connection_id)
    if connection_id is None:
        return
    now = now or timezone.now()
    if reason not in END_REASONS:
        raise ValueError('Invalid disconnect reason')
    device_id = get_request_device_id(request)
    # Lock in the same order as heartbeat/revocation.
    device = UserDevice.objects.select_for_update().filter(pk=device_id, user=request.user).first()
    if device is None:
        return
    terminal = reason != 'disconnect' if terminal is None else terminal
    leases = list(PresenceConnection.objects.select_related('interval').filter(
        connection_id=connection_id, user=request.user, device_key=device_id,
    ))
    if not leases and terminal:
        for scope in request_scopes(request):
            PresenceConnection.objects.get_or_create(
                connection_id=connection_id, user=request.user, device_key=device_id, scope_hash=scope_hash(scope),
                defaults={'last_seen': now, 'is_active': False, 'is_terminal': True},
            )
    for lease in leases:
        interval = (SessionConnectionInterval.objects.select_for_update().get(pk=lease.interval_id)
                    if lease.interval_id is not None else None)
        lease.is_active = False
        lease.is_terminal = lease.is_terminal or terminal
        lease.save(update_fields=['is_active', 'is_terminal'])
        if interval is not None and interval.closed_at is None and not _fresh(interval, now):
            _finish(interval, now=now, reason=reason, ended_at=now)


@transaction.atomic
def end_device(device, *, reason='revoked', now=None):
    now = now or timezone.now()
    UserDevice.objects.select_for_update().filter(pk=device.pk).first()
    intervals = SessionConnectionInterval.objects.select_for_update().filter(
        user_id=device.user_id, device_key=device.pk, closed_at__isnull=True,
    )
    for interval in intervals:
        interval.connections.update(is_terminal=True)
        _finish(interval, now=now, reason=reason, ended_at=now)


def maintain_history(*, now=None):
    now = now or timezone.now()
    with transaction.atomic():
        for interval in SessionConnectionInterval.objects.select_for_update().filter(
            closed_at__isnull=True, last_seen__lte=cutoff(now),
        ):
            _expire(interval, now)
        deleted, _ = SessionConnectionInterval.objects.filter(
            closed_at__lt=now - timedelta(days=RETENTION_DAYS),
        ).delete()
    PresenceConnection.objects.filter(interval__isnull=True, last_seen__lt=now - timedelta(days=RETENTION_DAYS)).delete()
    return deleted


def _scoped(scope):
    return SessionConnectionInterval.objects.filter(scope_hash=scope_hash(scope))


def summary(*, scope, actor_refs, now=None):
    now = now or timezone.now()
    rows = _scoped(scope).filter(user__public_id__in=actor_refs).values('user__public_id').annotate(last_seen=Max('last_seen'))
    fresh_users = {str(ref) for ref in _scoped(scope).filter(
        closed_at__isnull=True, connections__is_active=True,
        connections__last_seen__gt=cutoff(now), user__public_id__in=actor_refs,
    ).values_list('user__public_id', flat=True)}
    latest = {}
    for row in rows:
        latest[str(row['user__public_id'])] = row['last_seen'].isoformat()
    return {
        'as_of': now.isoformat(),
        'employees': [
            {'employee': str(ref), 'is_online': str(ref) in fresh_users,
             'last_seen': latest.get(str(ref))}
            for ref in actor_refs
        ],
    }


def history(*, scope, actor_ref, start, end, page=1, page_size=20, now=None):
    now = now or timezone.now()
    start = max(start, now - timedelta(days=RETENTION_DAYS))
    rows = _scoped(scope).filter(
        user__public_id=actor_ref, started_at__lte=end,
    ).filter(Q(last_seen__gte=start) | Q(ended_at__gte=start)).annotate(
        has_fresh_connection=Exists(PresenceConnection.objects.filter(
            interval_id=OuterRef('pk'), is_active=True, last_seen__gt=cutoff(now),
        )),
    ).order_by('-started_at', '-pk')
    count = rows.count()
    first = _scoped(scope).filter(user__public_id=actor_ref).order_by('started_at').first()
    results = []
    for row in rows[(page - 1) * page_size:page * page_size]:
        online = row.closed_at is None and row.has_fresh_connection
        timed_out = row.closed_at is None and not online
        results.append({
            'public_id': str(row.public_id), 'device_name': row.device_name,
            'device_type': row.device_type, 'browser': row.browser, 'os': row.os,
            'ip_address': row.ip_address, 'started_at': row.started_at.isoformat(),
            'last_seen': row.last_seen.isoformat(),
            'ended_at': row.ended_at.isoformat() if row.ended_at else None,
            'end_reason': 'timeout' if timed_out else row.end_reason,
            'is_online': online,
        })
    return {'as_of': now.isoformat(), 'count': count, 'results': results,
            'available_from': max(first.started_at, now - timedelta(days=RETENTION_DAYS)).isoformat() if first else None}
