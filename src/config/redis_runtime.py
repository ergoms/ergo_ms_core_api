"""
Сценарий REDIS_ENABLED: единая сборка URL для кэша и channel layer.
"""

from __future__ import annotations

from src.config.env import env


def redis_enabled() -> bool:
    return env.bool('REDIS_ENABLED', default=False)


def redis_host() -> str:
    return env.str('REDIS_HOST', default='127.0.0.1').strip() or '127.0.0.1'


def redis_port() -> int:
    raw = env.str('REDIS_PORT', default='6379').strip() or '6379'
    try:
        return int(raw)
    except ValueError:
        return 6379


def redis_db_cache() -> int:
    raw = env.str('REDIS_DB_CACHE', default='1').strip() or '1'
    try:
        return int(raw)
    except ValueError:
        return 1


def redis_db_channel() -> int:
    raw = env.str('REDIS_DB_CHANNEL', default='0').strip() or '0'
    try:
        return int(raw)
    except ValueError:
        return 0


def redis_url(db: int) -> str:
    return f'redis://{redis_host()}:{redis_port()}/{db}'


def cache_redis_url() -> str:
    explicit = env.str('API_CACHE_REDIS_URL', default='').strip()
    if explicit:
        return explicit
    return redis_url(redis_db_cache())


def channel_layer_redis_url() -> str:
    explicit = env.str('CHANNEL_LAYER_REDIS_URL', default='').strip()
    if explicit:
        return explicit
    return redis_url(redis_db_channel())


def redis_connection_options() -> dict[str, int]:
    """
    Параметры redis-py для Django cache.

    Portable Redis 5.x на Windows (tporadowski) не поддерживает RESP3/HELLO;
    redis-py 8+ без protocol=2 падает с «unknown command HELLO».
    """
    return {'protocol': 2}


def redis_channel_connection_options() -> dict[str, int | None]:
    """
    Параметры redis-py для channels_redis (SSE/WebSocket push).

    socket_timeout=None обязателен: channels_redis ждёт сообщения через BZPOPMIN
    с brpop_timeout=5 с; дефолтный socket_timeout redis-py (5 с) обрывает чтение
    раньше и даёт TimeoutError в логах SSE.
    """
    return {
        'protocol': 2,
        'socket_timeout': None,
    }
