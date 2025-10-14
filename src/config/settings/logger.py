"""
Файл содержащий конфигурацию логирования для Django-приложения.
Он включает настройки форматирования, обработчиков и логгеров для записи логов в файл и консоль.
"""

import os

from src.config.settings.base import LOGS_ROOT

import warnings
from sklearn.exceptions import InconsistentVersionWarning

# Отключаем предупреждения scikit-learn о несовместимости версий
warnings.filterwarnings("ignore", category=InconsistentVersionWarning)

# Создаем директорию для логов, если она не существует
os.makedirs(LOGS_ROOT, exist_ok=True)

# Проверяем права на запись
log_file = os.path.join(LOGS_ROOT, 'debug.log')
try:
    with open(log_file, 'a') as f:
        # Записываем пустую строку в файл
        f.write('')
except Exception as e:
    print(f"ОШИБКА: Невозможно записать в файл лога {log_file}: {str(e)}")
    raise

# Конфигурация логирования для Django-приложения.
LOGGING = {
    # Версия конфигурации логирования.
    'version': 1,

    # Флаг, указывающий, отключать ли существующие логгеры.
    'disable_existing_loggers': False,

    # Форматтеры для логов.
    'formatters': {
        # Подробный форматтер, включающий уровень логирования, время, модуль и сообщение.
        'verbose': {
            'format': '[{levelname}] {asctime} {name} {module} {message}',
            'style': '{',
            'datefmt': '%Y-%m-%d %H:%M:%S'
        },

        # Простой форматтер, включающий только уровень логирования и сообщение.
        'simple': {
            'format': '[{levelname}] {name}: {message}',
            'style': '{',
        },
    },

    # Обработчики для логов.
    'handlers': {
        # Обработчик для записи логов в файл.
        'file': {
            'level': 'INFO',
            'class': 'logging.FileHandler',
            'filename': os.path.join(LOGS_ROOT, 'debug.log'),
            'formatter': 'verbose',
            'encoding': 'utf-8',
        },

        # Обработчик для записи логов в консоль.
        'console': {
            'level': 'INFO',
            'class': 'logging.StreamHandler',
            'formatter': 'simple',
        },
        
        # Обработчики для Celery
        'celery_file': {
            'level': 'DEBUG',
            'class': 'logging.handlers.RotatingFileHandler',
            'filename': os.path.join(LOGS_ROOT, 'celery.log'),
            'formatter': 'verbose',
            'encoding': 'utf-8',
            'maxBytes': 10*1024*1024,  # 10MB
            'backupCount': 5,
            'delay': True,
        },
        
        'celery_worker_file': {
            'level': 'DEBUG',
            'class': 'logging.handlers.RotatingFileHandler',
            'filename': os.path.join(LOGS_ROOT, 'celery_worker.log'),
            'formatter': 'verbose',
            'encoding': 'utf-8',
            'maxBytes': 10*1024*1024,  # 10MB
            'backupCount': 5,
            'delay': True,
        },
        
        'celery_beat_file': {
            'level': 'DEBUG',
            'class': 'logging.handlers.RotatingFileHandler',
            'filename': os.path.join(LOGS_ROOT, 'celery_beat.log'),
            'formatter': 'verbose',
            'encoding': 'utf-8',
            'maxBytes': 10*1024*1024,  # 10MB
            'backupCount': 5,
            'delay': True,
        },
        
        'celery_tasks_file': {
            'level': 'DEBUG',
            'class': 'logging.handlers.RotatingFileHandler',
            'filename': os.path.join(LOGS_ROOT, 'celery_tasks.log'),
            'formatter': 'verbose',
            'encoding': 'utf-8',
            'maxBytes': 10*1024*1024,  # 10MB
            'backupCount': 5,
            'delay': True,
        },

        # Специальные обработчики для разнесения логов по файлам
        'video_analysis_file': {
            'level': 'DEBUG',
            'class': 'logging.handlers.RotatingFileHandler',
            'filename': os.path.join(LOGS_ROOT, 'video_analysis.log'),
            'formatter': 'verbose',
            'encoding': 'utf-8',
            'maxBytes': 10*1024*1024,  # 10MB
            'backupCount': 5,
            'delay': True,
        },
        'porosity_tasks_file': {
            'level': 'DEBUG',
            'class': 'logging.handlers.RotatingFileHandler',
            'filename': os.path.join(LOGS_ROOT, 'porosity_tasks.log'),
            'formatter': 'verbose',
            'encoding': 'utf-8',
            'maxBytes': 10*1024*1024,  # 10MB
            'backupCount': 5,
            'delay': True,
        },
        
        'celery_error_console': {
            'level': 'ERROR',
            'class': 'logging.StreamHandler',
            'formatter': 'verbose',
        },
    },

    # Логгеры для различных частей приложения.
    'loggers': {
        # Корневой логгер
        '': {
            'handlers': ['console'],
            'level': 'DEBUG',
            'propagate': True,
        },
        'django': {
            'handlers': ['console'],
            'level': 'INFO',
            'propagate': False,
        },
        'config': {
            'handlers': ['console'],
            'level': 'DEBUG',
            'propagate': False,
        },
        'config.database': {
            'handlers': ['console'],
            'level': 'DEBUG',
            'propagate': False,
        },
        'commands': {
            'handlers': ['console'],
            'level': 'INFO',
            'propagate': False,
        },
        'core.utils': {
            'handlers': ['console'],
            'level': 'INFO',
            'propagate': False,
        },
        'core.utils.commands': {
            'handlers': ['console'],
            'level': 'INFO',
            'propagate': False,
        },
        'core.utils.server': {
            'handlers': ['console'],
            'level': 'INFO',
            'propagate': False,
        },
        
        # Логгеры для Celery
        'celery': {
            'handlers': ['celery_file', 'console'],
            'level': 'DEBUG',
            'propagate': False,
        },
        
        'celery.worker': {
            'handlers': ['celery_worker_file', 'console'],
            'level': 'DEBUG',
            'propagate': False,
        },
        
        'celery.beat': {
            'handlers': ['celery_beat_file', 'console'],
            'level': 'DEBUG',
            'propagate': False,
        },
        
        'celery.task': {
            'handlers': ['celery_tasks_file', 'console'],
            'level': 'DEBUG',
            'propagate': False,
        },
        
        'celery.task.porosity_analysis': {
            'handlers': ['porosity_tasks_file', 'console'],
            'level': 'DEBUG',
            'propagate': False,
        },
        
        'celery.task.video_analysis': {
            'handlers': ['video_analysis_file', 'console'],
            'level': 'DEBUG',
            'propagate': False,
        },
        
        # Логгеры для модулей Celery
        'celery.module': {
            'handlers': ['celery_tasks_file', 'console', 'celery_error_console'],
            'level': 'DEBUG',
            'propagate': True,
        },
        
        # Логгер для модуля video_analysis
        'video_analysis': {
            'handlers': ['video_analysis_file', 'console'],
            'level': 'DEBUG',
            'propagate': False,
        },
        
        'celery.beat.module': {
            'handlers': ['celery_beat_file', 'console', 'celery_error_console'],
            'level': 'DEBUG',
            'propagate': True,
        },
        
        'kombu': {
            'handlers': ['celery_file', 'console'],
            'level': 'INFO',
            'propagate': False,
        },
    },
}