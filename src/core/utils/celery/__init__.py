"""
Пакет для управления конфигурациями Celery модулей.
"""

from src.core.utils.celery.base import CeleryModuleConfig
from src.core.utils.celery.manager import CeleryModuleManager

__all__ = ['CeleryModuleConfig', 'CeleryModuleManager'] 