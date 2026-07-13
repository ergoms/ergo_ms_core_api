"""
Сценарий REDIS_ENABLED: единая сборка URL для кэша, channel layer и Celery.
"""

from __future__ import annotations

from urllib.parse import urlsplit, urlunsplit

from src.config.env import env

_KOMBU_REDIS_RESP2_PATCHED = False


def redis_enabled() -> bool:
    return env.bool('REDIS_ENABLED', default=False)


def effective_cache_backend() -> str:
    explicit = env.str('API_CACHE_BACKEND', default='').strip().lower()
    if explicit:
        return explicit
    if redis_enabled():
        return 'redis'
    return 'locmem'


def effective_channel_layer_backend() -> str:
    explicit = env.str('CHANNEL_LAYER_BACKEND', default='').strip().lower()
    if explicit:
        return explicit
    if redis_enabled():
        return 'redis'
    return 'memory'


def effective_celery_broker_backend() -> str:
    explicit = env.str('CELERY_BROKER_BACKEND', default='').strip().lower()
    if explicit:
        return explicit
    if redis_enabled():
        return 'redis'
    return 'auto'


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


def redis_db_celery_broker() -> int:
    raw = env.str('REDIS_DB_CELERY_BROKER', default='2').strip() or '2'
    try:
        return int(raw)
    except ValueError:
        return 2


def redis_db_celery_result() -> int:
    raw = env.str('REDIS_DB_CELERY_RESULT', default='3').strip() or '3'
    try:
        return int(raw)
    except ValueError:
        return 3


def redis_url(db: int) -> str:
    return f'redis://{redis_host()}:{redis_port()}/{db}'


def sanitize_celery_redis_url(url: str) -> str:
    """
    Убирает query-параметры из URL Celery broker/result.

    ``?protocol=2`` нужен redis-py (Django cache), но kombu передаёт query в
    Connection._init_params() и падает с unexpected keyword argument 'protocol'.
    RESP2 для Celery задаётся через ensure_kombu_redis_resp2().
    """
    parts = urlsplit(url)
    if not parts.query:
        return url
    return urlunsplit((parts.scheme, parts.netloc, parts.path, '', parts.fragment))


def _celery_redis_url(db: int) -> str:
    return redis_url(db)


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


def celery_broker_redis_url() -> str:
    explicit = env.str('CELERY_BROKER_URL', default='').strip()
    if explicit:
        return sanitize_celery_redis_url(explicit)
    return _celery_redis_url(redis_db_celery_broker())


def celery_result_redis_url() -> str:
    explicit = env.str('CELERY_RESULT_BACKEND', default='').strip()
    if explicit:
        return sanitize_celery_redis_url(explicit)
    return _celery_redis_url(redis_db_celery_result())


def uses_redis_celery_backend(broker_url: str, result_backend: str = '') -> bool:
    for url in (broker_url, result_backend):
        if url.startswith('redis://') or url.startswith('rediss://'):
            return True
    return False


def ensure_kombu_redis_resp2() -> None:
    """
    Старый portable Redis 5.x на Windows не поддерживал RESP3/HELLO; redis-py 8+ по
    умолчанию шлёт HELLO. Kombu не принимает ``protocol`` в query URL — прокидываем
    в pool. На Redis 7+ патч безвреден.
    """
    global _KOMBU_REDIS_RESP2_PATCHED
    if _KOMBU_REDIS_RESP2_PATCHED:
        return

    from kombu.transport import redis as kombu_redis_transport

    original_connparams = kombu_redis_transport.Channel._connparams

    def _connparams_with_resp2(self, asynchronous=False):
        params = original_connparams(self, asynchronous=asynchronous)
        params['protocol'] = 2
        return params

    kombu_redis_transport.Channel._connparams = _connparams_with_resp2
    _KOMBU_REDIS_RESP2_PATCHED = True


def redis_connection_options() -> dict[str, int]:
    """
    Параметры redis-py для Django cache.

    Portable Redis 5.x на Windows не поддерживал RESP3/HELLO; redis-py 8+ без
    protocol=2 падал с «unknown command HELLO». На Redis 7+ (ergoms install-redis)
    protocol=2 остаётся совместимым.
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
