"""
Файл содержащий настройки для продакшн (production) окружения Django-приложения.

Он импортирует базовые настройки из модуля `local` и добавляет специфические настройки для продакшн,
такие как секретный ключ, режим отладки и разрешенные хосты.
"""

from src.config.patterns.local import *
from src.config.env import env
from src.config.nginx_runtime import merge_allowed_hosts, nginx_enabled, nginx_use_https

SECRET_KEY = env.str('API_SECRET_KEY')

DEBUG = False

ALLOWED_HOSTS = merge_allowed_hosts(
    env.list('API_ALLOWED_HOSTS', default=['localhost', '127.0.0.1']),
)

# Редирект HTTP -> HTTPS (включать только если перед приложением нет прокси с TLS)
SECURE_SSL_REDIRECT = env.bool('SECURE_SSL_REDIRECT', default=False)

# HSTS: браузер обращается к сайту только по HTTPS (1 год, включая поддомены, разрешён preload)
SECURE_HSTS_SECONDS = 31536000
SECURE_HSTS_INCLUDE_SUBDOMAINS = True
SECURE_HSTS_PRELOAD = True

# Secure cookies (HTTP за nginx без TLS — cookies без Secure)
_cookie_secure = not (nginx_enabled() and not nginx_use_https())
SESSION_COOKIE_SECURE = _cookie_secure
SESSION_COOKIE_HTTPONLY = True
SESSION_COOKIE_SAMESITE = 'Lax'
CSRF_COOKIE_SECURE = _cookie_secure
CSRF_COOKIE_HTTPONLY = True
CSRF_COOKIE_SAMESITE = 'Lax'

SECURE_PROXY_SSL_HEADER = ('HTTP_X_FORWARDED_PROTO', 'https')