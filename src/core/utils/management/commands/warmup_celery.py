"""
Прогрев только celery-кэшей: discovered_apps, celery_routes_queues,
celery_queues, celery_beat_schedule.

Быстрее чем warmup_caches — не заполняет modules_env.
Тонкая обёртка над run_file_cache_warmup для call_command внутри Django.
"""
import logging
import time

from django.core.management.base import BaseCommand

from src.core.utils.warmup_file_caches import run_file_cache_warmup

logger = logging.getLogger('core.utils.commands')


class Command(BaseCommand):
    help = 'Прогрев celery-кэшей (без modules_env) для быстрого старта worker и Beat'

    def handle(self, *args, **options):
        start = time.perf_counter()
        result = run_file_cache_warmup(include_modules_env=False)
        self.stdout.write(f'Обнаружено приложений: {result["apps"]}')
        self.stdout.write(
            f'Celery: {result["routes"]} маршрутов, {result["queues"]} очередей'
        )
        self.stdout.write(f'Расписание Beat: {result["beat_tasks"]} задач')
        elapsed = time.perf_counter() - start
        self.stdout.write(self.style.SUCCESS(f'Celery кэши прогреты ({elapsed:.2f}s)'))
