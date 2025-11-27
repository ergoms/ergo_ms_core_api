"""
Основной конфигурационный файл Celery для Django-приложения.
Отвечает за инициализацию Celery и автоматическое обнаружение задач.

Функциональность:
    - Инициализация Celery приложения
    - Настройка интеграции с Django
    - Автоматическое обнаружение задач из установленных приложений
    - Модульная система конфигурации
"""

import os
from pathlib import Path

from celery import Celery

from django.conf import settings

from src.core.utils.auto_api.auto_config import get_env_deploy_type
from src.core.utils.celery.manager import CeleryModuleManager
from src.core.utils.celery_beat.manager import CeleryBeatModuleManager
from src.config.settings.base import LOGS_ROOT, VIRTUAL_ENV_DIR

# Определение типа развертывания и настройка переменной окружения Django
deploy_type = get_env_deploy_type()
os.environ.setdefault('DJANGO_SETTINGS_MODULE', deploy_type)

# Определяем, запускается ли beat (проверяем аргументы командной строки)
import sys
import logging
logger = logging.getLogger('config.celery')

is_beat = 'beat' in sys.argv or 'celery beat' in ' '.join(sys.argv)

# Инициализация Celery приложения
celery_app = Celery('src')

# Если запускается beat, используем настройки beat, иначе worker
if is_beat:
    logger.info("Celery: Запускается BEAT, используются настройки CELERY_BEAT_*")
    # Для beat загружаем настройки с префиксом CELERY_BEAT_
    celery_app.config_from_object('django.conf:settings', namespace='CELERY_BEAT')
    # Но также добавляем общие настройки CELERY_
    from django.conf import settings as django_settings
    for key in dir(django_settings):
        if key.startswith('CELERY_') and not key.startswith('CELERY_BEAT_'):
            celery_app.conf[key.replace('CELERY_', '').lower()] = getattr(django_settings, key)
else:
    logger.info("Celery: Запускается WORKER, используются настройки CELERY_*")
    # Для worker используем стандартные CELERY_ настройки
    celery_app.config_from_object('django.conf:settings', namespace='CELERY')

celery_app.autodiscover_tasks(lambda: settings.INSTALLED_APPS)

# Инициализация менеджера модулей
module_manager = CeleryModuleManager()
logger.info("Celery: Загружены конфигурации модулей: %s", ", ".join(module_manager.get_modules_list()))

# Собираем маршруты и очереди модулей
module_task_routes = module_manager.get_all_task_routes()
module_task_queues = module_manager.get_all_task_queues()

# Гарантируем наличие очереди по умолчанию
if 'default' not in module_task_queues:
    module_task_queues['default'] = {
        'exchange': 'default',
        'routing_key': 'default',
    }

# Fallback-маршрут для задач без явного роутинга
if '*' not in module_task_routes and 'default' in module_task_queues:
    module_task_routes['*'] = {'queue': 'default'}

# ПРИМЕЧАНИЕ: CeleryBeatModuleManager инициализируется в config/settings/celery_beat.py
# и автоматически загружается через namespace='CELERY_BEAT' (строка 42)

# Настройка логирования Celery
def setup_celery_logging():
    """Настраивает основное логирование для Celery"""
    import logging
    from logging.handlers import RotatingFileHandler
    
    # Создаем директорию для логов если её нет
    os.makedirs(LOGS_ROOT, exist_ok=True)
    
    # Пути к файлам логов
    celery_log_file = os.path.join(LOGS_ROOT, 'celery.log')
    celery_worker_log_file = os.path.join(LOGS_ROOT, 'celery_worker.log')
    celery_beat_log_file = os.path.join(LOGS_ROOT, 'celery_beat.log')
    celery_tasks_log_file = os.path.join(LOGS_ROOT, 'celery_tasks.log')
    
    # Настройка форматтера для логов
    log_formatter = logging.Formatter(
        '[%(asctime)s] %(levelname)s [%(name)s.%(funcName)s:%(lineno)d] %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )
    
    # Основной логгер Celery
    celery_logger = logging.getLogger('celery')
    celery_logger.setLevel(logging.DEBUG)
    
    # Хендлер для файла
    celery_file_handler = RotatingFileHandler(
        celery_log_file,
        maxBytes=10*1024*1024,  # 10MB
        backupCount=5,
        encoding='utf-8'
    )
    celery_file_handler.setLevel(logging.DEBUG)
    celery_file_handler.setFormatter(log_formatter)
    celery_logger.addHandler(celery_file_handler)
    
    # Логгер для воркеров
    worker_logger = logging.getLogger('celery.worker')
    worker_logger.setLevel(logging.DEBUG)
    
    worker_file_handler = RotatingFileHandler(
        celery_worker_log_file,
        maxBytes=10*1024*1024,  # 10MB
        backupCount=5,
        encoding='utf-8'
    )
    worker_file_handler.setLevel(logging.DEBUG)
    worker_file_handler.setFormatter(log_formatter)
    worker_logger.addHandler(worker_file_handler)
    
    # Логгер для beat (планировщик)
    beat_logger = logging.getLogger('celery.beat')
    beat_logger.setLevel(logging.DEBUG)
    
    beat_file_handler = RotatingFileHandler(
        celery_beat_log_file,
        maxBytes=10*1024*1024,  # 10MB
        backupCount=5,
        encoding='utf-8'
    )
    beat_file_handler.setLevel(logging.DEBUG)
    beat_file_handler.setFormatter(log_formatter)
    beat_logger.addHandler(beat_file_handler)
    
    # Логгер для задач
    tasks_logger = logging.getLogger('celery.task')
    tasks_logger.setLevel(logging.DEBUG)
    
    tasks_file_handler = RotatingFileHandler(
        celery_tasks_log_file,
        maxBytes=10*1024*1024,  # 10MB
        backupCount=5,
        encoding='utf-8'
    )
    tasks_file_handler.setLevel(logging.DEBUG)
    tasks_file_handler.setFormatter(log_formatter)
    tasks_logger.addHandler(tasks_file_handler)
    
    # Логгер для брокера
    broker_logger = logging.getLogger('kombu')
    broker_logger.setLevel(logging.INFO)
    
    broker_file_handler = RotatingFileHandler(
        os.path.join(LOGS_ROOT, 'celery_broker.log'),
        maxBytes=5*1024*1024,  # 5MB
        backupCount=3,
        encoding='utf-8'
    )
    broker_file_handler.setLevel(logging.INFO)
    broker_file_handler.setFormatter(log_formatter)
    broker_logger.addHandler(broker_file_handler)

    # В разработке добавляем консольный вывод
    console_handler = logging.StreamHandler()
    console_handler.setLevel(logging.INFO)
    console_handler.setFormatter(log_formatter)
    celery_logger.addHandler(console_handler)
    worker_logger.addHandler(console_handler)
    beat_logger.addHandler(console_handler)
    tasks_logger.addHandler(console_handler)

# Настраиваем логирование Celery
setup_celery_logging()

# Настройка пути к файлу состояния планировщика и периодических задач
# Broker URL и Result Backend берутся из config/settings/celery.py и celery_beat.py автоматически

# Импортируем настройки Beat напрямую из модуля (не через Django settings)
CELERY_BEAT_SCHEDULER = None
CELERY_BEAT_SCHEDULER_DB_ALIAS = None
CELERY_BEAT_SCHEDULE_FILENAME = str(VIRTUAL_ENV_DIR / "celery" / "celerybeat-schedule.db")
CELERY_BEAT_SCHEDULE = {}

if is_beat:
    try:
        # Импортируем НАПРЯМУЮ из модуля celery_beat
        import src.config.settings.celery_beat as beat_settings
        
        CELERY_BEAT_SCHEDULER = getattr(beat_settings, 'CELERY_BEAT_SCHEDULER', None)
        CELERY_BEAT_SCHEDULER_DB_ALIAS = getattr(beat_settings, 'CELERY_BEAT_SCHEDULER_DB_ALIAS', None)
        CELERY_BEAT_SCHEDULE_FILENAME = getattr(beat_settings, 'CELERY_BEAT_SCHEDULE_FILENAME', 
                                                  str(VIRTUAL_ENV_DIR / "celery" / "celerybeat-schedule.db"))
        CELERY_BEAT_SCHEDULE = getattr(beat_settings, 'CELERY_BEAT_SCHEDULE', {})
        
        logger.info(f"Beat: Импортировано расписаний: {len(CELERY_BEAT_SCHEDULE)}")
        if CELERY_BEAT_SCHEDULE:
            logger.info(f"Beat: Задачи: {', '.join(CELERY_BEAT_SCHEDULE.keys())}")
    except Exception as e:
        logger.error(f"Beat: Ошибка загрузки расписаний: {e}")

# Формируем конфигурацию Beat scheduler
beat_scheduler_config = {}
if CELERY_BEAT_SCHEDULER:
    # Используем django-celery-beat
    beat_scheduler_config['beat_scheduler'] = CELERY_BEAT_SCHEDULER
    if CELERY_BEAT_SCHEDULER_DB_ALIAS:
        beat_scheduler_config['beat_scheduler_db_alias'] = CELERY_BEAT_SCHEDULER_DB_ALIAS
else:
    # Используем локальный файл
    beat_scheduler_config['beat_schedule_filename'] = CELERY_BEAT_SCHEDULE_FILENAME

# Применяем расписания задач к конфигурации Beat
if is_beat and CELERY_BEAT_SCHEDULE:
    beat_scheduler_config['beat_schedule'] = CELERY_BEAT_SCHEDULE
    logger.info(f"Beat: Применено {len(CELERY_BEAT_SCHEDULE)} расписаний в конфигурацию Celery")

celery_app.conf.update(
    **beat_scheduler_config,
    
    # Маршруты задач из всех модулей
    task_routes=module_task_routes,
    
    task_default_queue='default',
    
    # Очереди задач из всех модулей
    task_queues=module_task_queues,
    
    # Аннотации задач из всех модулей
    task_annotations=module_manager.get_all_task_annotations(),
    
    # Настройки воркеров
    task_acks_late=True,  # Подтверждаем задачи только после выполнения
    
    # Настройки логирования Celery
    worker_log_format='[%(asctime)s: %(levelname)s/%(processName)s] %(message)s',
    worker_task_log_format='[%(asctime)s: %(levelname)s/%(processName)s][%(task_name)s(%(task_id)s)] %(message)s',
    worker_log_color=False,
    worker_redirect_stdouts=False,
    worker_redirect_stdouts_level='INFO',
    
    # Дополнительные настройки из модулей
    **module_manager.get_additional_configs()
)

# ==================== Синхронизация задач с БД ====================
# Синхронизируем задачи из конфига с БД при использовании DatabaseScheduler
# Выполняется только при запуске beat, после полной инициализации Django
if is_beat and CELERY_BEAT_SCHEDULER and CELERY_BEAT_SCHEDULER_DB_ALIAS and CELERY_BEAT_SCHEDULE:
    try:
        # Убеждаемся, что Django полностью инициализирован
        import django
        from django.apps import apps
        
        # Проверяем, инициализирован ли Django
        if not apps.ready:
            django.setup()
        
        from src.core.utils.celery_beat.sync import CeleryBeatSyncManager
        
        logger.info("Beat: Начало синхронизации задач с БД...")
        logger.info(f"Beat: db_alias={CELERY_BEAT_SCHEDULER_DB_ALIAS}, задач в конфиге={len(CELERY_BEAT_SCHEDULE)}")
        
        sync_manager = CeleryBeatSyncManager(
            config_schedule=CELERY_BEAT_SCHEDULE,
            db_alias=CELERY_BEAT_SCHEDULER_DB_ALIAS
        )
        sync_results = sync_manager.sync_all()
        
        logger.info(
            f"Beat: Синхронизация задач с БД завершена - "
            f"создано: {sync_results['created']}, "
            f"обновлено: {sync_results['updated']}, "
            f"удалено: {sync_results['deleted']}"
        )
    except Exception as e:
        logger.error(f"Beat: Ошибка синхронизации задач с БД: {e}", exc_info=True)
        # Не прерываем запуск, но логируем ошибку