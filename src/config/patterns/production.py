"""
Файл содержащий настройки для продакшн (production) окружения Django-приложения.

Он импортирует базовые настройки из модуля `local` и добавляет специфические настройки для продакшн,
такие как секретный ключ, режим отладки и разрешенные хосты.
"""

from src.config.patterns.local import *
from src.config.env import env

SECRET_KEY = env.str('API_SECRET_KEY')

DEBUG = False

ALLOWED_HOSTS = env.list('API_ALLOWED_HOSTS', default=['localhost', '127.0.0.1'])

# Редирект HTTP -> HTTPS (включать только если перед приложением нет прокси с TLS)
SECURE_SSL_REDIRECT = env.bool('SECURE_SSL_REDIRECT', default=False)

# HSTS: браузер обращается к сайту только по HTTPS (1 год, включая поддомены, разрешён preload)
SECURE_HSTS_SECONDS = 31536000
SECURE_HSTS_INCLUDE_SUBDOMAINS = True
SECURE_HSTS_PRELOAD = True