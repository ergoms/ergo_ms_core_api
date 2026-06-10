"""
Файл содержащий конфигурацию сервера для Django-приложения.
Он включает настройки имени процесса сервера, хоста и порта.
"""

from src.config.env import env
from src.core.utils.os_abstraction import get_os_abstraction

# Имя процесса сервера с учетом операционной системы.
SERVER_PROCESS_NAME = get_os_abstraction().server_process_name('daphne')

# Хост сервера, полученный из переменной окружения.
SERVER_HOST = env.str('API_HOST', default='localhost')

# Порт сервера, полученный из переменной окружения.
SERVER_PORT = env.str('API_PORT', default='8000')

# Хост и порт клиентского приложения.
CLIENT_HOST = env.str('CLIENT_HOST', default='localhost')
CLIENT_PORT = env.str('CLIENT_PORT', default='8001')

# Базовый URL клиентского приложения (deep-link в email-уведомлениях и т.п.).
# Строится из CLIENT_HOST/CLIENT_PORT; для production за доменом/https
# можно переопределить целиком через FRONTEND_BASE_URL.
FRONTEND_BASE_URL = env.str(
    'FRONTEND_BASE_URL',
    default=f'http://{CLIENT_HOST}:{CLIENT_PORT}',
)