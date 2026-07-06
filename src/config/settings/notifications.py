"""Настройки уведомлений (кэш счётчика)."""

from src.config.env import env

# TTL кэша unread_count (секунды); 0 — отключить
NOTIFICATIONS_UNREAD_CACHE_TTL = env.int('API_NOTIFICATIONS_UNREAD_CACHE_TTL', default=45)
