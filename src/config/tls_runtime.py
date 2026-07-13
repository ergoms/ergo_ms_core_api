"""
Effective TLS-пути и домены из .env и стандартных каталогов Let's Encrypt.

Скрипты развёртывания не должны записывать эти значения в .env — читайте отсюда.
"""

from __future__ import annotations

from pathlib import Path

from src.config.env import env
from src.config.nginx_runtime import nginx_public_host, nginx_use_https

LE_LIVE_DIR = Path('/etc/letsencrypt/live')


def primary_tls_domain() -> str:
    raw = env.str('ERGO_TLS_DOMAINS', default='').strip()
    if raw:
        return raw.split(',')[0].strip()

    host = nginx_public_host()
    if host and host not in ('localhost', '127.0.0.1'):
        return host

    return env.str('NGINX_SERVER_NAME', default='').strip()


def cert_paths(domain: str) -> tuple[str, str]:
    base = LE_LIVE_DIR / domain
    return str(base / 'fullchain.pem'), str(base / 'privkey.pem')


def cert_exists(domain: str) -> bool:
    fullchain, privkey = cert_paths(domain)
    return Path(fullchain).is_file() and Path(privkey).is_file()


def effective_ssl_cert() -> str:
    explicit = env.str('ERGO_SSL_CERT', default='').strip()
    if explicit:
        return explicit

    if not nginx_use_https():
        return ''

    domain = primary_tls_domain()
    if domain and cert_exists(domain):
        return cert_paths(domain)[0]
    return ''


def effective_ssl_key() -> str:
    explicit = env.str('ERGO_SSL_KEY', default='').strip()
    if explicit:
        return explicit

    if not nginx_use_https():
        return ''

    domain = primary_tls_domain()
    if domain and cert_exists(domain):
        return cert_paths(domain)[1]
    return ''
