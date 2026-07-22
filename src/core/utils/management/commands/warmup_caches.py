"""
Прогрев всех файловых кэшей:
- discovered_apps, celery_routes_queues, celery_queues
- celery_beat_schedule
- modules_env

Тонкая обёртка над run_file_cache_warmup для call_command внутри Django.
Основной путь ergoms — script-команда без django.setup().
"""
import logging
import time

from django.core.management.base import BaseCommand

from src.core.utils.warmup_file_caches import run_file_cache_warmup

logger = logging.getLogger('core.utils.commands')


class Command(BaseCommand):
    help = 'Прогрев всех файловых кэшей для быстрого старта API, Celery worker и Beat'

    def handle(self, *args, **options):
        start = time.perf_counter()
        result = run_file_cache_warmup(include_modules_env=True)
        self.stdout.write(f'Обнаружено приложений: {result["apps"]}')
        self.stdout.write(
            f'Celery: {result["routes"]} маршрутов, {result["queues"]} очередей'
        )
        self.stdout.write(f'Расписание Beat: {result["beat_tasks"]} задач')
        if result.get('modules_env'):
            self.stdout.write(f'Переменные модулей: {result["modules_env"]}')
        elapsed = time.perf_counter() - start
        self.stdout.write(self.style.SUCCESS(f'Все кэши прогреты ({elapsed:.2f}s)'))
