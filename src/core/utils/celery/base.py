"""
Базовый класс для конфигурации Celery модулей.
Позволяет каждому модулю настраивать свои собственные задачи и логирование.
"""

import logging

from abc import ABC, abstractmethod
from typing import Dict, Any


class CeleryModuleConfig(ABC):
    """
    Базовый класс для конфигурации Celery модулей.
    Каждый модуль должен наследоваться от этого класса и реализовать необходимые методы.
    """

    def __init__(self, module_name: str):
        self.module_name = module_name

    @abstractmethod
    def get_task_routes(self) -> Dict[str, Dict[str, Any]]:
        """
        Возвращает маршруты задач для модуля.
        Пример: {'src.modules.my_module.tasks.*': {'queue': 'my_module'}}
        """
        pass

    @abstractmethod
    def get_task_queues(self) -> Dict[str, Dict[str, Any]]:
        """
        Возвращает настройки очередей для модуля.
        Пример: {'my_module': {'exchange': 'my_module', 'routing_key': 'my_module'}}
        """
        pass

    @abstractmethod
    def get_task_annotations(self) -> Dict[str, Dict[str, Any]]:
        """
        Возвращает аннотации задач для модуля.
        Пример: {'src.modules.my_module.tasks.my_task': {'time_limit': 3600}}
        """
        pass

    def get_module_loggers(self) -> Dict[str, logging.Logger]:
        """
        Возвращает логгеры для модуля (handlers задаёт dictConfig в logging_config).
        Записи попадают в logs/celery_tasks.log; фильтр: celery.module.<имя>.
        """
        return {
            'main': logging.getLogger(f'celery.module.{self.module_name}'),
            'tasks': logging.getLogger(f'celery.module.{self.module_name}.tasks'),
            'worker': logging.getLogger(f'celery.module.{self.module_name}.worker'),
        }

    def get_additional_config(self) -> Dict[str, Any]:
        """
        Возвращает дополнительные настройки для модуля.
        Переопределите этот метод, если нужны дополнительные настройки.
        """
        return {}

    def get_max_concurrent_tasks(self) -> int:
        """
        Возвращает максимальное количество одновременных задач для очереди модуля.
        Переопределите этот метод для ограничения параллелизма задач модуля.

        Returns:
            int: Максимальное количество одновременных задач. 0 означает без ограничений.
        """
        return 0

    def get_queue_name(self) -> str:
        """
        Возвращает имя очереди для модуля.
        По умолчанию совпадает с именем модуля.
        """
        queues = self.get_task_queues()
        if queues:
            return list(queues.keys())[0]
        return self.module_name
