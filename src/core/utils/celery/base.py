"""
Базовый класс для конфигурации Celery модулей.
Позволяет каждому модулю настраивать свои собственные задачи и логирование.
"""

import os
import logging

from abc import ABC, abstractmethod
from typing import Dict, Any

from src.config.settings.static import LOGS_ROOT

class CeleryModuleConfig(ABC):
    """
    Базовый класс для конфигурации Celery модулей.
    Каждый модуль должен наследоваться от этого класса и реализовать необходимые методы.
    """
    
    def __init__(self, module_name: str):
        self.module_name = module_name
        self.log_dir = self._get_log_dir()
        self._setup_module_logging()
    
    def _get_log_dir(self) -> str:
        """Получает путь к директории логов"""
        log_dir = os.path.join(LOGS_ROOT, 'modules', self.module_name)
        os.makedirs(log_dir, exist_ok=True)
        return log_dir
    
    def _setup_module_logging(self):
        """Настраивает логирование для модуля"""
        # Используем Django логирование
        module_logger = logging.getLogger(f'celery.module.{self.module_name}')
        
        # Проверяем, есть ли уже обработчики у логгера
        if not module_logger.handlers:
            # Создаем файловый обработчик для модуля
            log_file = os.path.join(self.log_dir, f'{self.module_name}.log')
            file_handler = logging.FileHandler(
                log_file,
                encoding='utf-8'
            )
            file_handler.setLevel(logging.DEBUG)
            
            # Форматтер для логов
            log_formatter = logging.Formatter(
                f'[%(asctime)s] %(levelname)s [%(name)s.%(funcName)s:%(lineno)d] [{self.module_name}] %(message)s',
                datefmt='%Y-%m-%d %H:%M:%S'
            )
            file_handler.setFormatter(log_formatter)
            module_logger.addHandler(file_handler)
            
            # Добавляем консольный обработчик для ошибок
            console_handler = logging.StreamHandler()
            console_handler.setLevel(logging.ERROR)
            console_handler.setFormatter(log_formatter)
            module_logger.addHandler(console_handler)
    
    @abstractmethod
    def get_task_routes(self) -> Dict[str, str]:
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
        Возвращает логгеры для модуля.
        Переопределите этот метод, если нужны дополнительные логгеры.
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