"""Настройки кэша собранного меню пользователя."""

from src.config.env import env

# TTL кэша меню (секунды); 0 — отключить серверный кэш
MENU_CACHE_TTL = env.int('API_MENU_CACHE_TTL', default=300)
