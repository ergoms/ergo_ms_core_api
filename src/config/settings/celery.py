"""
Файл содержащий конфигурацию Celery для Django-приложения.
Включает настройки брокера сообщений SQLite, сериализации задач и временной зоны.

Настройки:
    CELERY_BROKER_URL: URL-адрес брокера сообщений SQLite
    CELERY_RESULT_BACKEND: URL-адрес бэкенда для хранения результатов задач

    CELERY_ACCEPT_CONTENT: Список разрешенных форматов сериализации
    CELERY_TASK_SERIALIZER: Формат сериализации для задач
    CELERY_RESULT_SERIALIZER: Формат сериализации для результатов
    CELERY_TIMEZONE: Временная зона для планировщика задач
    CELERY_BROKER_CONNECTION_RETRY_ON_STARTUP: Флаг повторного подключения к брокеру при запуске
"""

from core.api.src.config.settings.base import VIRTUAL_ENV_DIR

CELERY_BROKER_URL = f'sqla+sqlite:///{VIRTUAL_ENV_DIR}/celery/celerydb.sqlite'
CELERY_RESULT_BACKEND = f'db+sqlite:///{VIRTUAL_ENV_DIR}/celery/results.sqlite'

CELERY_ACCEPT_CONTENT = ['json']
CELERY_TASK_SERIALIZER = 'json'
CELERY_RESULT_SERIALIZER = 'json'
CELERY_TIMEZONE = 'UTC'
CELERY_BROKER_CONNECTION_RETRY_ON_STARTUP = True