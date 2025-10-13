"""
Общая конфигурация Celery Beat.
Собирает расписания задач из всех модулей.
"""

from src.core.utils.celery_beat.manager import CeleryBeatModuleManager

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