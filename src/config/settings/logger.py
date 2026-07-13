"""
Конфигурация логирования Django-приложения (API + Celery через dictConfig).
"""

import sys

from src.config.logging_config import build_logging_config
from src.config.log_paths import resolve_logging_service

LOGGING = build_logging_config(resolve_logging_service(sys.argv))
