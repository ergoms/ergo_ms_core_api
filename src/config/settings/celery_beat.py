"""
Общая конфигурация Celery Beat.
Собирает расписания задач из всех модулей.
Использует централизованную объектно-ориентированную систему управления БД.
"""

import logging

from src.core.utils.celery_beat.manager import CeleryBeatModuleManager

# Импортируем централизованный менеджер БД для Celery Beat
from src.core.utils.database.config_manager import CeleryDatabaseConfigLoader
from src.config.settings.base import VIRTUAL_ENV_DIR, SYSTEM_DIR

logger = logging.getLogger('config.celery_beat')

# ==================== Конфигурация БД для Celery Beat ====================

# Создаем загрузчик для Celery Beat (приоритет: celery_beat -> celery -> локальный)
beat_db_loader = CeleryDatabaseConfigLoader(
    system_dir=SYSTEM_DIR,
    virtual_env_dir=VIRTUAL_ENV_DIR,
    section_priorities=['celery_beat', 'celery'],
    component_name="Celery Beat"
)

# Загружаем конфигурацию
beat_db_config = beat_db_loader.load_config()

# Настройки брокера и backend для Beat
CELERY_BEAT_BROKER_URL = beat_db_config['broker_url']
CELERY_BEAT_RESULT_BACKEND = beat_db_config['result_backend']

# ==================== Конфигурация scheduler для Beat ====================

# Определяем, где хранить расписание
db_alias = beat_db_loader.get_django_db_alias()

if db_alias is not None:
    # Используем django-celery-beat для хранения расписания в БД
    CELERY_BEAT_SCHEDULER = 'django_celery_beat.schedulers:DatabaseScheduler'
    CELERY_BEAT_SCHEDULER_DB_ALIAS = db_alias
    logger.info(f"Celery Beat: Расписание хранится в БД '{db_alias}' (django-celery-beat)")
else:
    # Используем локальный файл
    CELERY_BEAT_SCHEDULE_FILENAME = str(VIRTUAL_ENV_DIR / "celery" / "celerybeat-schedule.db")
    logger.info(f"Celery Beat: Расписание хранится в файле {CELERY_BEAT_SCHEDULE_FILENAME}")

# Логируем активную конфигурацию
if beat_db_config['mode'] == 'database':
    logger.info(f"Celery Beat: Используется БД '{beat_db_config['section']}' ({beat_db_config['engine']})")
else:
    logger.info("Celery Beat: Используется локальный SQLite режим")

# ==================== Расписание задач из модулей ====================

# Инициализируем менеджер Beat модулей
beat_module_manager = CeleryBeatModuleManager()

# Собираем все расписания из модулей
CELERY_BEAT_SCHEDULE = beat_module_manager.get_all_beat_schedules()

# Дополнительные настройки Beat из модулей
CELERY_BEAT_ADDITIONAL_CONFIG = beat_module_manager.get_additional_beat_configs()

# Логгеры Beat модулей
CELERY_BEAT_MODULE_LOGGERS = beat_module_manager.get_module_loggers()

# Список загруженных модулей Beat
CELERY_BEAT_MODULES = beat_module_manager.get_modules_list() 