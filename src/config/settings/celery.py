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

CELERY_BROKER_URL = 'sqla+sqlite:///celery/celerydb.sqlite'
CELERY_RESULT_BACKEND = 'db+sqlite:///celery/results.sqlite'

CELERY_ACCEPT_CONTENT = ['json']
CELERY_TASK_SERIALIZER = 'json'
CELERY_RESULT_SERIALIZER = 'json'
CELERY_TIMEZONE = 'UTC'
CELERY_BROKER_CONNECTION_RETRY_ON_STARTUP = True