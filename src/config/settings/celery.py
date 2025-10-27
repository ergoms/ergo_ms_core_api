"""
Файл содержащий конфигурацию Celery для Django-приложения.
Включает настройки брокера сообщений и результатов задач с поддержкой 
различных СУБД из databases.yaml или локального SQLite.
Использует централизованную объектно-ориентированную систему управления БД.

Настройки:
    CELERY_BROKER_URL: URL-адрес брокера сообщений
    CELERY_RESULT_BACKEND: URL-адрес бэкенда для хранения результатов задач

    CELERY_ACCEPT_CONTENT: Список разрешенных форматов сериализации
    CELERY_TASK_SERIALIZER: Формат сериализации для задач
    CELERY_RESULT_SERIALIZER: Формат сериализации для результатов
    CELERY_TIMEZONE: Временная зона для планировщика задач
    CELERY_BROKER_CONNECTION_RETRY_ON_STARTUP: Флаг повторного подключения к брокеру при запуске

Режимы работы:
    - Приоритет 1: celery_worker или celery_beat (для worker/beat соответственно)
    - Приоритет 2: celery (общая секция)
    - Fallback: локальный SQLite
    - Можно принудительно включить локальный режим через CELERY_USE_LOCAL=true
"""

import logging
from core.api.src.config.settings.base import VIRTUAL_ENV_DIR, SYSTEM_DIR

# Импортируем централизованный менеджер БД для Celery
from src.core.utils.database.config_manager import CeleryDatabaseConfigLoader

logger = logging.getLogger('config.celery')

# ==================== Конфигурация для Celery Worker ====================

# Создаем загрузчик для Celery Worker (приоритет: celery_worker -> celery -> локальный)
worker_loader = CeleryDatabaseConfigLoader(
    system_dir=SYSTEM_DIR,
    virtual_env_dir=VIRTUAL_ENV_DIR,
    section_priorities=['celery_worker', 'celery'],
    component_name="Celery Worker"
)

# Загружаем конфигурацию
worker_config = worker_loader.load_config()

# Устанавливаем переменные для Django settings
CELERY_BROKER_URL = worker_config['broker_url']
CELERY_RESULT_BACKEND = worker_config['result_backend']

# Логируем активную конфигурацию
if worker_config['mode'] == 'database':
    logger.info(f"Celery Worker: Используется БД '{worker_config['section']}' ({worker_config['engine']})")
else:
    logger.info("Celery Worker: Используется локальный SQLite режим")

# ==================== Общие настройки Celery ====================

CELERY_ACCEPT_CONTENT = ['json']
CELERY_TASK_SERIALIZER = 'json'
CELERY_RESULT_SERIALIZER = 'json'
CELERY_TIMEZONE = 'UTC'
CELERY_BROKER_CONNECTION_RETRY_ON_STARTUP = True