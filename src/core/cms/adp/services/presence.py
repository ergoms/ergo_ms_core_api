from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta

from django.conf import settings
from django.db.models import F
from django.utils import timezone

from src.core.cms.adp.models import UserPresence

PRESENCE_BATCH_LIMIT = 100


@dataclass(frozen=True)
class PresenceEntry:
    is_online: bool
    last_seen: datetime | None


def get_presence_stale_threshold_seconds() -> int:
    interval = getattr(settings, 'REALTIME_POLL_PRESENCE_INTERVAL', 45)
    return interval * 2


def get_presence_stale_cutoff() -> datetime:
    return timezone.now() - timedelta(seconds=get_presence_stale_threshold_seconds())


def effective_is_online(presence: UserPresence) -> bool:
    if presence.connection_count <= 0:
        return False
    if presence.last_seen is None:
        return False
    return presence.last_seen >= get_presence_stale_cutoff()


def _maybe_cleanup_stale(presence: UserPresence) -> UserPresence:
    if presence.connection_count > 0 and not effective_is_online(presence):
        UserPresence.objects.filter(pk=presence.pk).update(connection_count=0)
        presence.connection_count = 0
    return presence


def _to_entry(presence: UserPresence) -> PresenceEntry:
    presence = _maybe_cleanup_stale(presence)
    return PresenceEntry(
        is_online=effective_is_online(presence),
        last_seen=presence.last_seen,
    )


def _offline_entry() -> PresenceEntry:
    return PresenceEntry(is_online=False, last_seen=None)


def register_connection(user_id: int) -> PresenceEntry:
    now = timezone.now()
    presence, _ = UserPresence.objects.get_or_create(
        user_id=user_id,
        defaults={'connection_count': 0, 'last_seen': now},
    )
    UserPresence.objects.filter(pk=presence.pk).update(
        connection_count=F('connection_count') + 1,
        last_seen=now,
    )
    presence.refresh_from_db(fields=['connection_count', 'last_seen'])
    entry = _to_entry(presence)
    _broadcast_presence_delta(user_id, entry)
    return entry


def unregister_connection(user_id: int) -> PresenceEntry:
    now = timezone.now()
    try:
        presence = UserPresence.objects.get(user_id=user_id)
    except UserPresence.DoesNotExist:
        return _offline_entry()

    new_count = max(0, presence.connection_count - 1)
    UserPresence.objects.filter(pk=presence.pk).update(
        connection_count=new_count,
        last_seen=now,
    )
    presence.refresh_from_db(fields=['connection_count', 'last_seen'])
    entry = _to_entry(presence)
    _broadcast_presence_delta(user_id, entry)
    return entry


def _broadcast_presence_delta(user_id: int, entry: PresenceEntry) -> None:
    from src.core.cms.adp.services.presence_realtime import publish_presence_delta

    publish_presence_delta(
        user_id,
        serialize_presence_entry(entry),
        public_id=resolve_public_id(user_id),
    )


def touch(user_id: int) -> PresenceEntry:
    now = timezone.now()
    updated = UserPresence.objects.filter(user_id=user_id).update(last_seen=now)
    if not updated:
        return _offline_entry()
    presence = UserPresence.objects.get(user_id=user_id)
    return _to_entry(presence)


def http_heartbeat(user_id: int) -> PresenceEntry:
    """HTTP polling: регистрация сессии при первом heartbeat, далее touch."""
    try:
        presence = UserPresence.objects.get(user_id=user_id)
    except UserPresence.DoesNotExist:
        return register_connection(user_id)
    if presence.connection_count == 0:
        return register_connection(user_id)
    return touch(user_id)


def reset_user(user_id: int) -> None:
    now = timezone.now()
    UserPresence.objects.filter(user_id=user_id).update(
        connection_count=0,
        last_seen=now,
    )


def http_offline(user_id: int) -> PresenceEntry:
    """HTTP polling: сброс виртуальной сессии (не decrement WS-подключений)."""
    reset_user(user_id)
    try:
        presence = UserPresence.objects.get(user_id=user_id)
    except UserPresence.DoesNotExist:
        entry = _offline_entry()
        _broadcast_presence_delta(user_id, entry)
        return entry
    entry = _to_entry(presence)
    _broadcast_presence_delta(user_id, entry)
    return entry


def get_presence_map(user_ids: list[int] | None = None) -> dict[int, PresenceEntry]:
    if user_ids is not None:
        normalized_ids = list(dict.fromkeys(int(uid) for uid in user_ids if uid is not None))
        if not normalized_ids:
            return {}

        existing = {
            presence.user_id: _to_entry(presence)
            for presence in UserPresence.objects.filter(user_id__in=normalized_ids)
        }
        return {
            user_id: existing.get(user_id, _offline_entry())
            for user_id in normalized_ids
        }

    return {
        presence.user_id: _to_entry(presence)
        for presence in UserPresence.objects.all()
    }


def get_presence_map_by_public_ids(
    public_ids: list[str],
) -> dict[str, PresenceEntry]:
    """Карта presence, keyed по строковому public_id (UUID)."""
    from django.contrib.auth import get_user_model

    User = get_user_model()
    normalized = list(dict.fromkeys(pid for pid in public_ids if pid))
    if not normalized:
        return {}

    id_pairs = list(
        User.objects.filter(public_id__in=normalized).values_list('id', 'public_id')
    )
    pk_by_public = {str(public_id): pk for pk, public_id in id_pairs}
    presence_by_pk = get_presence_map(list(pk_by_public.values())) if pk_by_public else {}

    result: dict[str, PresenceEntry] = {}
    for public_id in normalized:
        pk = pk_by_public.get(public_id)
        if pk is None:
            result[public_id] = _offline_entry()
        else:
            result[public_id] = presence_by_pk.get(pk, _offline_entry())
    return result


def serialize_presence_entry(entry: PresenceEntry) -> dict:
    return {
        'is_online': entry.is_online,
        'last_seen': entry.last_seen.isoformat() if entry.last_seen else None,
    }


def serialize_presence_map(presence_map: dict) -> dict[str, dict]:
    """Сериализация карты; ключи — str(user_id) или public_id."""
    return {
        str(key): serialize_presence_entry(entry)
        for key, entry in presence_map.items()
    }


def _public_ids_for_user_pks(user_ids: list[int]) -> dict[int, str]:
    from django.contrib.auth import get_user_model

    User = get_user_model()
    if not user_ids:
        return {}
    return {
        pk: str(public_id)
        for pk, public_id in User.objects.filter(pk__in=user_ids).values_list('id', 'public_id')
        if public_id
    }


def resolve_public_id(user_id: int) -> str | None:
    mapping = _public_ids_for_user_pks([user_id])
    return mapping.get(user_id)


def build_presence_snapshot(presence_map: dict[int, PresenceEntry] | None = None) -> list[dict]:
    if presence_map is None:
        presence_map = get_presence_map()

    public_map = _public_ids_for_user_pks(list(presence_map.keys()))
    return [
        {
            'public_id': public_map.get(user_id),
            **serialize_presence_entry(entry),
        }
        for user_id, entry in presence_map.items()
        if public_map.get(user_id)
    ]


def parse_public_ids_param(raw: str | None, *, limit: int = PRESENCE_BATCH_LIMIT) -> list[str]:
    if not raw:
        return []

    result: list[str] = []
    for part in raw.split(','):
        part = part.strip()
        if not part or part in result:
            continue
        # UUID / opaque public_id — не числовой pk
        if part.isdigit():
            continue
        result.append(part)
        if len(result) >= limit:
            break
    return result


def parse_user_ids_param(raw: str | None, *, limit: int = PRESENCE_BATCH_LIMIT) -> list[int]:
    """Устаревший alias: числовые pk. Предпочтите parse_public_ids_param."""
    if not raw:
        return []

    result: list[int] = []
    for part in raw.split(','):
        part = part.strip()
        if not part:
            continue
        try:
            user_id = int(part)
        except (TypeError, ValueError):
            continue
        if user_id > 0 and user_id not in result:
            result.append(user_id)
        if len(result) >= limit:
            break
    return result
