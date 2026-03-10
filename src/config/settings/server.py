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