"""
Файл содержащий конфигурацию сервера для Django-приложения.
Он включает настройки имени процесса сервера, хоста и порта.
"""

from src.config.env import env

# Имя процесса сервера.
SERVER_PROCESS_NAME = 'daphne.exe'

# Хост сервера, полученный из переменной окружения.
SERVER_HOST = env.str('API_HOST', default='localhost')

# Порт сервера, полученный из переменной окружения.
SERVER_PORT = env.str('API_PORT', default='8000')