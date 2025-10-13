"""
Конфигурация Celery Beat для модуля bi_analysis.
Настройки периодических задач бизнес-аналитики.
"""

from typing import Dict, Any
from celery.schedules import crontab

from src.core.utils.celery_beat.base import CeleryBeatModuleConfig

class BIAnalysisBeatConfig(CeleryBeatModuleConfig):
    """
    Конфигурация Celery Beat для модуля бизнес-аналитики.
    """
    
    def get_beat_schedule(self) -> Dict[str, Dict[str, Any]]:
        """Расписание периодических задач для бизнес-аналитики"""
        return {
            'sync-data-every-5-minutes': {
                'task': 'src.core.bi_analysis.tasks.sync_data_from_sources',
                'schedule': crontab(minute='*/5'),
            },
        }
    
    def get_additional_beat_config(self) -> Dict[str, Any]:
        """Дополнительные настройки Beat для модуля бизнес-аналитики"""
        return {
            'bi_analysis_beat_max_tasks_per_worker': 3,
            'bi_analysis_beat_task_timeout': 1800,  # 30 минут
            'bi_analysis_beat_retry_delay': 300,  # 5 минут
        } 