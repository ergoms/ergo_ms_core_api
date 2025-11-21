"""
Конфигурация Celery для модуля bi_analysis.
Настройки задач бизнес-аналитики и их логирование.
"""

from typing import Dict, Any
from src.core.utils.celery.base import CeleryModuleConfig


class BIAnalysisCeleryConfig(CeleryModuleConfig):
    """
    Конфигурация Celery для модуля бизнес-аналитики.
    """
    
    def get_task_routes(self) -> Dict[str, Dict[str, Any]]:
        """Маршруты задач для бизнес-аналитики"""
        return {
            'src.core.bi_analysis.tasks.*': {'queue': 'bi_analysis'},
        }
    
    def get_task_queues(self) -> Dict[str, Dict[str, Any]]:
        """Очереди задач для бизнес-аналитики"""
        return {
            'bi_analysis': {
                'exchange': 'bi_analysis',
                'routing_key': 'bi_analysis',
            }
        }
    
    def get_task_annotations(self) -> Dict[str, Dict[str, Any]]:
        """Аннотации задач для бизнес-аналитики"""
        return {
            'src.core.bi_analysis.tasks.sync_data_from_sources': {
                'time_limit': 1800,   # Таймаут 30 минут
                'soft_time_limit': 1500,  # Мягкий таймаут 25 минут
            },
        }
    
    def get_module_loggers(self) -> Dict[str, Any]:
        """Специализированные логгеры для модуля бизнес-аналитики"""
        loggers = super().get_module_loggers()
        
        # Добавляем специализированные логгеры
        loggers.update({
            'sync': self._get_logger('sync'),
        })
        
        return loggers
    
    def _get_logger(self, logger_name: str):
        """Создает специализированный логгер для модуля"""
        import logging
        return logging.getLogger(f'celery.module.{self.module_name}.{logger_name}')
    
    def get_additional_config(self) -> Dict[str, Any]:
        """Дополнительные настройки для модуля бизнес-аналитики"""
        return {
            # Специфичные настройки для бизнес-аналитики
            'bi_analysis_max_concurrent_tasks': 3,
            'bi_analysis_data_retention_days': 730,  # 2 года
            'bi_analysis_report_generation_interval': 86400,  # 24 часа
        } 