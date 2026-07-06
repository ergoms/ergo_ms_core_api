"""
Файл содержащий конфигурацию сервера для Django-приложения.
Он включает настройки имени процесса сервера, хоста и порта.
"""

from src.config.env import env
from src.config.nginx_runtime import (
    effective_api_bind_host,
    nginx_enabled,
    nginx_public_base_url,
    nginx_public_host,
)
from src.core.utils.os_abstraction import get_os_abstraction

# Имя процесса сервера с учетом операционной системы.
SERVER_PROCESS_NAME = get_os_abstraction().server_process_name('daphne')

# Хост сервера, полученный из переменной окружения.
SERVER_HOST = effective_api_bind_host('localhost')

# Порт сервера, полученный из переменной окружения.
SERVER_PORT = env.str('API_PORT', default='8000')

# Хост и порт клиентского приложения.
CLIENT_HOST = env.str('CLIENT_HOST', default='localhost')
CLIENT_PORT = env.str('CLIENT_PORT', default='8001')

# Базовый URL клиентского приложения (deep-link в email-уведомлениях и т.п.).
# При NGINX_ENABLED=true — публичный URL nginx (NGINX_PUBLIC_HOST).
FRONTEND_BASE_URL = (
    nginx_public_base_url()
    if nginx_enabled()
    else env.str('FRONTEND_BASE_URL', default=f'http://{CLIENT_HOST}:{CLIENT_PORT}')
)

# Публичный хост nginx (для подсказок и интеграций).
NGINX_PUBLIC_HOST = nginx_public_host() if nginx_enabled() else ''

# Сжатие JSON-ответов (GZipMiddleware). При nginx+brotli можно отключить.
API_GZIP_ENABLED = env.bool('API_GZIP_ENABLED', default=True)