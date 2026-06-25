"""
Сценарий NGINX_ENABLED: единая точка входа, внутренние сервисы на 127.0.0.1.

Публичный адрес задаётся NGINX_PUBLIC_HOST (IP или hostname).
NGINX_SERVER_NAME — fallback и server_name в конфиге nginx.
"""

from __future__ import annotations

from src.config.env import env


def detect_lan_ip() -> str:
    import socket

    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
            sock.connect(('8.8.8.8', 80))
            ip = sock.getsockname()[0]
            if ip and not ip.startswith('127.'):
                return ip
    except OSError:
        pass

    try:
        hostname = socket.gethostname()
        ip = socket.gethostbyname(hostname)
        if ip and not ip.startswith('127.'):
            return ip
    except OSError:
        pass

    return ''


def nginx_enabled() -> bool:
    return env.bool('NGINX_ENABLED', default=False)


def nginx_public_host() -> str:
    explicit = env.str('NGINX_PUBLIC_HOST', default='').strip()
    if explicit:
        return explicit

    server_name = env.str('NGINX_SERVER_NAME', default='localhost').strip()
    if nginx_enabled() and server_name in ('', 'localhost', '127.0.0.1'):
        detected = detect_lan_ip()
        if detected:
            return detected

    return server_name or 'localhost'


def nginx_listen_host() -> str:
    return env.str('NGINX_LISTEN_HOST', default='0.0.0.0').strip() or '0.0.0.0'


def nginx_listen_port() -> str:
    return env.str('NGINX_LISTEN_PORT', default='80').strip() or '80'


def nginx_use_https() -> bool:
    if env.bool('NGINX_USE_HTTPS', default=False):
        return True
    return nginx_listen_port() == '443'


def nginx_public_base_url() -> str:
    override = env.str('FRONTEND_BASE_URL', default='').strip()
    if override and not nginx_enabled():
        return override.rstrip('/')

    scheme = 'https' if nginx_use_https() else 'http'
    host = nginx_public_host()
    port = nginx_listen_port()
    if (scheme == 'http' and port == '80') or (scheme == 'https' and port == '443'):
        return f'{scheme}://{host}'
    return f'{scheme}://{host}:{port}'


def nginx_public_origin() -> str:
    return nginx_public_base_url()


def merge_allowed_hosts(hosts: list[str] | tuple[str, ...]) -> list[str]:
    merged = list(hosts)
    if not nginx_enabled():
        return merged
    for item in (nginx_public_host(), 'localhost', '127.0.0.1'):
        if item and item not in merged:
            merged.append(item)
    return merged


def effective_api_bind_host(default: str = 'localhost') -> str:
    if nginx_enabled():
        return env.str('API_HOST', default='127.0.0.1')
    return env.str('API_HOST', default=default)


def effective_media_public_host(default: str = 'localhost') -> str:
    if nginx_enabled():
        return env.str('MEDIA_API_HOST', default=nginx_public_host())
    return env.str('MEDIA_API_HOST', default=default)


def effective_media_public_port(default: str = '8003') -> str:
    if nginx_enabled():
        return env.str('MEDIA_API_PORT', default=nginx_listen_port())
    return env.str('MEDIA_API_PORT', default=default)


def effective_cors_origins(default_origins: list[str]) -> list[str]:
    if not nginx_enabled():
        return default_origins
    origin = nginx_public_origin()
    if origin in default_origins:
        return default_origins
    return [origin, *default_origins]
