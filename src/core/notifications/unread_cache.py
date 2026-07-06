"""Кэш счётчика непрочитанных уведомлений."""

from django.conf import settings
from django.core.cache import cache

UNREAD_CACHE_KEY_PREFIX = 'notifications:unread:'


def get_unread_cache_ttl() -> int:
    return max(0, int(getattr(settings, 'NOTIFICATIONS_UNREAD_CACHE_TTL', 45) or 0))


def _unread_cache_key(user_id: int) -> str:
    return f'{UNREAD_CACHE_KEY_PREFIX}{user_id}'


def invalidate_unread_count_cache(user_id: int | None) -> None:
    if user_id is None:
        return
    cache.delete(_unread_cache_key(int(user_id)))


def get_cached_unread_count(user_id: int) -> int | None:
    ttl = get_unread_cache_ttl()
    if ttl <= 0:
        return None
    cached = cache.get(_unread_cache_key(user_id))
    if cached is None:
        return None
    return int(cached)


def set_cached_unread_count(user_id: int, count: int) -> None:
    ttl = get_unread_cache_ttl()
    if ttl <= 0:
        return
    cache.set(_unread_cache_key(user_id), int(count), timeout=ttl)
