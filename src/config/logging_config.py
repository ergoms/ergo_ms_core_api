"""
Фабрика LOGGING для API и Celery: файлы всегда, консоль — по ERGO_LOG_CONSOLE*.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import Any

from src.config.log_paths import (
    file_level_for_key,
    log_basename,
    read_log_level_env,
    resolve_logs_root,
    resolve_logging_service,
    rotation_settings,
    service_levels,
)
from src.config.settings.base import ENV_FILE_PATH, SYSTEM_DIR


def _rotating_handler(level: str, filename: str, max_bytes: int, backup_count: int) -> dict[str, Any]:
    return {
        'level': level,
        'formatter': 'verbose',
        'filename': filename,
        'class': 'logging.handlers.RotatingFileHandler',
        'maxBytes': max_bytes,
        'backupCount': backup_count,
        'encoding': 'utf-8',
        'delay': True,
    }


def _console_handler(level: str) -> dict[str, Any]:
    return {
        'level': level,
        'class': 'logging.StreamHandler',
        'formatter': 'simple',
    }


def _default_file_handler_key(service: str) -> str:
    """Файл по умолчанию для логгеров без явной регистрации (getLogger(__name__))."""
    if service == 'celery_beat':
        return 'celery_beat_file'
    if service == 'celery':
        return 'celery_worker_file'
    return 'api_file'


def build_logging_config(service: str | None = None) -> dict[str, Any]:
    if service is None:
        service = resolve_logging_service(sys.argv)

    logs_root = str(resolve_logs_root(SYSTEM_DIR))
    os.makedirs(logs_root, exist_ok=True)
    env_file = Path(ENV_FILE_PATH)

    file_level, console_level, console_enabled = service_levels(service, SYSTEM_DIR)
    rotation = rotation_settings(SYSTEM_DIR)
    service_prefix = service.upper().replace('-', '_')
    handlers: dict[str, Any] = {}

    def add_file(
        key: str,
        handler_key: str,
        level: str | None = None,
        *,
        max_bytes: int | None = None,
        backup_count: int | None = None,
    ):
        log_name = log_basename(key, SYSTEM_DIR)
        resolved_level = level or file_level_for_key(key, SYSTEM_DIR, service_prefix)
        handlers[handler_key] = _rotating_handler(
            resolved_level,
            os.path.join(logs_root, log_name),
            max_bytes or rotation['max_bytes'],
            backup_count if backup_count is not None else rotation['backup_count'],
        )

    add_file('API', 'api_file')
    add_file('CELERY', 'celery_file')
    add_file('CELERY_WORKER', 'celery_worker_file')
    add_file('CELERY_BEAT', 'celery_beat_file')
    add_file('CELERY_TASKS', 'celery_tasks_file')
    add_file(
        'CELERY_BROKER',
        'celery_broker_file',
        max_bytes=rotation['broker_max_bytes'],
        backup_count=rotation['broker_backup_count'],
    )
    add_file('CLIENT_BROWSER', 'client_browser_file')
    add_file('AUDIT', 'audit_file')

    if console_enabled:
        handlers['console'] = _console_handler(console_level)
        handlers['celery_error_console'] = {
            'level': 'ERROR',
            'class': 'logging.StreamHandler',
            'formatter': 'verbose',
        }

    console = ['console'] if console_enabled else []
    celery_err = ['celery_error_console'] if console_enabled else []
    default_file = _default_file_handler_key(service)
    # При ERGO_LOG_CONSOLE=false (systemd) root без файла терял core.*, modules.*, daphne.*.
    root_handlers = [default_file] + console

    # Access (middleware) — INFO всегда, даже при ERGO_LOG_FILE_LEVEL=info.
    # Daphne http_protocol / environ — не ниже WARNING (иначе «мусорка» на DEBUG).
    api_loggers_common = ['api_file'] + console

    loggers: dict[str, Any] = {
        'django': {
            'handlers': api_loggers_common,
            'level': 'INFO',
            'propagate': False,
        },
        # Как у runserver: одна строка на HTTP-запрос
        'django.server': {
            'handlers': api_loggers_common,
            'level': 'INFO',
            'propagate': False,
        },
        'daphne': {
            'handlers': api_loggers_common,
            'level': 'INFO',
            'propagate': False,
        },
        'daphne.http_protocol': {
            'handlers': api_loggers_common,
            'level': 'WARNING',
            'propagate': False,
        },
        'daphne.http_disconnect': {
            'handlers': api_loggers_common,
            'level': 'WARNING',
            'propagate': False,
        },
        'environ': {
            'handlers': api_loggers_common,
            'level': 'WARNING',
            'propagate': False,
        },
        'environ.environ': {
            'handlers': api_loggers_common,
            'level': 'WARNING',
            'propagate': False,
        },
        'config': {
            'handlers': api_loggers_common,
            'level': 'DEBUG',
            'propagate': False,
        },
        'config.database': {
            'handlers': api_loggers_common,
            'level': 'DEBUG',
            'propagate': False,
        },
        'commands': {
            'handlers': api_loggers_common,
            'level': 'INFO',
            'propagate': False,
        },
        'core.utils': {
            'handlers': api_loggers_common,
            'level': 'INFO',
            'propagate': False,
        },
        'core.utils.commands': {
            'handlers': api_loggers_common,
            'level': 'INFO',
            'propagate': False,
        },
        'core.utils.server': {
            'handlers': api_loggers_common,
            'level': 'INFO',
            'propagate': False,
        },
        'client.browser': {
            'handlers': ['client_browser_file'],
            'level': read_log_level_env(
                'CLIENT_BROWSER_LOG_FILE_LEVEL',
                env_file,
                file_level_for_key('CLIENT_BROWSER', SYSTEM_DIR),
            ),
            'propagate': False,
        },
        'core.audit': {
            'handlers': ['audit_file'] + console,
            'level': 'DEBUG',
            'propagate': False,
        },
        'celery.core.audit': {
            'handlers': ['audit_file'] + console,
            'level': 'DEBUG',
            'propagate': False,
        },
        'celery': {
            'handlers': ['celery_file'] + console,
            'level': 'DEBUG',
            'propagate': False,
        },
        'celery.worker': {
            'handlers': ['celery_worker_file'] + console,
            'level': 'DEBUG',
            'propagate': False,
        },
        'celery.beat': {
            'handlers': ['celery_beat_file'] + console,
            'level': 'DEBUG',
            'propagate': False,
        },
        'celery.task': {
            'handlers': ['celery_tasks_file'] + console,
            'level': 'DEBUG',
            'propagate': False,
        },
        'celery.module': {
            'handlers': ['celery_tasks_file'] + console + celery_err,
            'level': 'DEBUG',
            'propagate': False,
        },
        'celery.beat.module': {
            'handlers': ['celery_beat_file'] + console + celery_err,
            'level': 'DEBUG',
            'propagate': False,
        },
        'kombu': {
            'handlers': ['celery_broker_file'] + console,
            'level': file_level_for_key('CELERY_BROKER', SYSTEM_DIR, service_prefix),
            'propagate': False,
        },
    }

    return {
        'version': 1,
        'disable_existing_loggers': False,
        'formatters': {
            'verbose': {
                'format': '[{levelname}] {asctime} {name} {module} {message}',
                'style': '{',
                'datefmt': '%Y-%m-%d %H:%M:%S',
            },
            'simple': {
                'format': '[{levelname}] {name}: {message}',
                'style': '{',
            },
        },
        'handlers': handlers,
        'root': {
            'handlers': root_handlers,
            'level': file_level,
        },
        'loggers': loggers,
    }


def build_api_logging_config() -> dict[str, Any]:
    return build_logging_config('api')
