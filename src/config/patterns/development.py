"""
Файл содержащий настройки для разработки (development) Django-приложения.

Он импортирует базовые настройки из модуля `local` и добавляет специфические настройки для разработки,
такие как секретный ключ, режим отладки и разрешенные хосты.
"""

from src.config.patterns.local import *
from src.config.env import env
from src.config.nginx_runtime import merge_allowed_hosts

SECRET_KEY = env.str('API_SECRET_KEY')

DEBUG = True

ALLOWED_HOSTS = merge_allowed_hosts(
    env.list('API_ALLOWED_HOSTS', default=['localhost', '127.0.0.1']),
)