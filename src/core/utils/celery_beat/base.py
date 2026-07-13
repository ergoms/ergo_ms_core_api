"""
Базовый класс для конфигурации Celery Beat модулей.
"""

import logging

from abc import ABC, abstractmethod
from typing import Any, Dict


class CeleryBeatModuleConfig(ABC):
    """
    Базовый класс для конфигурации Celery Beat модулей.
    Каждый модуль должен наследоваться от этого класса и реализовать необходимые методы.
    """

    def __init__(self, module_name: str):
        self.module_name = module_name

    @abstractmethod
    def get_beat_schedule(self) -> Dict[str, Dict[str, Any]]:
        """
        Возвращает расписание задач для модуля.

        Returns:
            Dict[str, Dict[str, Any]]: Словарь с расписанием задач
        """
        pass

    def get_additional_beat_config(self) -> Dict[str, Any]:
        """
        Возвращает дополнительные настройки Beat для модуля.

        Returns:
            Dict[str, Any]: Дополнительные настройки
        """
        return {}

    def get_module_loggers(self) -> Dict[str, logging.Logger]:
        """
        Возвращает логгеры модуля (handlers задаёт dictConfig в logging_config).
        Записи попадают в logs/celery_beat.log; фильтр: celery.beat.module.<имя>.
        """
        return {
            'main': logging.getLogger(f'celery.beat.module.{self.module_name}'),
        }
