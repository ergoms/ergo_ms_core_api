from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from django.db.models import F
from django.utils import timezone

from src.core.cms.adp.models import UserPresence

PRESENCE_BATCH_LIMIT = 100


@dataclass(frozen=True)
class PresenceEntry:
    is_online: bool
    last_seen: datetime | None


def _to_entry(presence: UserPresence) -> PresenceEntry:
    return PresenceEntry(
        is_online=presence.is_online,
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
    return _to_entry(presence)


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
    return _to_entry(presence)


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


def serialize_presence_entry(entry: PresenceEntry) -> dict:
    return {
        'is_online': entry.is_online,
        'last_seen': entry.last_seen.isoformat() if entry.last_seen else None,
    }


def serialize_presence_map(presence_map: dict[int, PresenceEntry]) -> dict[str, dict]:
    return {
        str(user_id): serialize_presence_entry(entry)
        for user_id, entry in presence_map.items()
    }


def build_presence_snapshot(presence_map: dict[int, PresenceEntry] | None = None) -> list[dict]:
    if presence_map is None:
        presence_map = get_presence_map()

    return [
        {
            'user_id': user_id,
            **serialize_presence_entry(entry),
        }
        for user_id, entry in presence_map.items()
    ]


def parse_user_ids_param(raw: str | None, *, limit: int = PRESENCE_BATCH_LIMIT) -> list[int]:
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
