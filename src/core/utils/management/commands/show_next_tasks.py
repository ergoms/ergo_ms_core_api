"""
Команда Django для отображения ближайших запланированных задач Celery Beat.

Пример использования:
>>> python src/manage.py show_next_tasks
>>> python src/manage.py show_next_tasks --count 10
"""

import logging
from datetime import datetime, timedelta
from typing import List, Tuple

from django.core.management.base import BaseCommand, CommandParser
from celery.schedules import crontab

logger = logging.getLogger('core.utils.commands')

class Command(BaseCommand):
    """
    Команда для отображения ближайших запланированных задач.
    """
    help = 'Показывает ближайшие запланированные задачи Celery Beat'

    def add_arguments(self, parser: CommandParser) -> None:
        """Добавляет аргументы командной строки."""
        parser.add_argument(
            '--count',
            type=int,
            default=5,
            help='Количество ближайших задач для показа (default: 5)'
        )

    def handle(self, *args: tuple, **options: dict) -> None:
        """Выполняет команду показа ближайших задач."""
        logger.info('Запуск команды show_next_tasks')
        
        from src.core.utils.celery_beat.manager import CeleryBeatModuleManager
        
        beat_manager = CeleryBeatModuleManager()
        schedules = beat_manager.get_all_beat_schedules()
        
        if not schedules:
            self.stdout.write(self.style.WARNING('Нет запланированных задач'))
            return
        
        now = datetime.now()
        next_runs: List[Tuple[datetime, str, str]] = []
        
        # Вычисляем следующие запуски для каждой задачи
        for task_name, task_config in schedules.items():
            schedule = task_config.get('schedule')
            if isinstance(schedule, crontab):
                next_run = self._get_next_run_time(schedule, now)
                if next_run:
                    next_runs.append((next_run, task_name, task_config['task']))
        
        # Сортируем по времени
        next_runs.sort(key=lambda x: x[0])
        
        # Выводим информацию
        self.stdout.write(self.style.SUCCESS(f'\n⏰ Текущее время: {now.strftime("%Y-%m-%d %H:%M:%S")}\n'))
        self.stdout.write(self.style.SUCCESS(f'📋 Ближайшие {options["count"]} задач:\n'))
        
        for i, (run_time, task_name, task_path) in enumerate(next_runs[:options['count']], 1):
            time_until = run_time - now
            hours = int(time_until.total_seconds() // 3600)
            minutes = int((time_until.total_seconds() % 3600) // 60)
            
            self.stdout.write(f'\n{i}. {self.style.SUCCESS("🚀 " + task_name)}')
            self.stdout.write(f'   ⏱️  Время запуска: {self.style.WARNING(run_time.strftime("%Y-%m-%d %H:%M"))}')
            self.stdout.write(f'   ⏳ Через: {self.style.WARNING(f"{hours}ч {minutes}мин")}')
            self.stdout.write(f'   📦 Задача: {task_path}')

    def _get_next_run_time(self, schedule: crontab, from_time: datetime) -> datetime:
        """Вычисляет следующее время запуска для crontab расписания."""
        # Проверяем следующие 7 дней
        for days_ahead in range(7):
            for hour in range(24):
                for minute in range(60):
                    check_time = from_time.replace(
                        hour=hour, 
                        minute=minute, 
                        second=0, 
                        microsecond=0
                    ) + timedelta(days=days_ahead)
                    
                    if check_time <= from_time:
                        continue
                    
                    if self._is_due(schedule, check_time):
                        return check_time
        
        return None

    def _is_due(self, schedule: crontab, check_time: datetime) -> bool:
        """Проверяет, должна ли задача запуститься в указанное время."""
        # Проверка минут
        if schedule.minute != set(range(60)):
            if check_time.minute not in schedule.minute:
                return False
        
        # Проверка часов
        if schedule.hour != set(range(24)):
            if check_time.hour not in schedule.hour:
                return False
        
        # Проверка дней месяца
        if schedule.day_of_month != set(range(1, 32)):
            if check_time.day not in schedule.day_of_month:
                return False
        
        # Проверка месяцев
        if schedule.month_of_year != set(range(1, 13)):
            if check_time.month not in schedule.month_of_year:
                return False
        
        # Проверка дней недели (0 = понедельник, 6 = воскресенье)
        if schedule.day_of_week != set(range(7)):
            weekday = check_time.weekday()
            if weekday not in schedule.day_of_week:
                return False
        
        return True

