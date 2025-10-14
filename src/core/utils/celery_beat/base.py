"""
Базовый класс для конфигурации Celery Beat модулей.
"""

import logging

from abc import ABC, abstractmethod
from typing import Dict, Any
from pathlib import Path

from src.config.settings.base import LOGS_ROOT

class CeleryBeatModuleConfig(ABC):
    """
    Базовый класс для конфигурации Celery Beat модулей.
    Каждый модуль должен наследоваться от этого класса и реализовать необходимые методы.
    """
    
    def __init__(self, module_name: str):
        self.module_name = module_name
        self.log_dir = self._get_log_dir()
        self._setup_module_logging()
    
    def _get_log_dir(self) -> Path:
        """Создает директорию для логов модуля"""
        log_dir = Path(LOGS_ROOT) / 'celery' / 'beat' / self.module_name
        log_dir.mkdir(parents=True, exist_ok=True)
        return log_dir
    
    def _setup_module_logging(self):
        """Настраивает базовое логирование для модуля"""
        import logging.handlers
        
        # Создаем основной логгер модуля
        logger = logging.getLogger(f'celery.beat.module.{self.module_name}')
        
        # Проверяем, есть ли уже обработчики у логгера
        if not logger.handlers:
            # Файловый обработчик с ротацией
            file_handler = logging.handlers.RotatingFileHandler(
                self.log_dir / 'beat.log',
                maxBytes=10*1024*1024,  # 10MB
                backupCount=5
            )
            file_handler.setLevel(logging.INFO)
            
            # Форматтер
            formatter = logging.Formatter(
                '[%(asctime)s: %(levelname)s/%(name)s] %(message)s'
            )
            file_handler.setFormatter(formatter)
            logger.addHandler(file_handler)
    
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
    
    def get_module_loggers(self) -> Dict[str, Any]:
        """
        Возвращает логгеры модуля.
        
        Returns:
            Dict[str, Any]: Словарь с логгерами
        """
        return {
            'main': logging.getLogger(f'celery.beat.module.{self.module_name}'),
        } 