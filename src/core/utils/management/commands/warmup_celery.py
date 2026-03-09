"""
Прогрев только celery-кэшей: discovered_apps, celery_routes_queues, celery_queues, celery_beat_schedule.

Быстрее чем warmup_caches — не заполняет modules_env.
"""
import logging
import time

from django.core.management.base import BaseCommand

logger = logging.getLogger('core.utils.commands')


class Command(BaseCommand):
    help = 'Прогрев celery-кэшей (без modules_env) для быстрого старта worker и Beat'

    def handle(self, *args, **options):
        start = time.perf_counter()

        from src.core.utils.auto_api.discovered_apps_cache import get_discovered_apps
        apps = get_discovered_apps(use_cache=False)
        self.stdout.write(f'Discovered apps: {len(apps)}')

        from src.core.utils.celery.manager import CeleryModuleManager
        from src.core.utils.celery_queues_cache import write_queues_cache

        manager = CeleryModuleManager(use_config_cache=False)
        routes = manager.get_all_task_routes()
        queues = manager.get_all_task_queues()

        write_queues_cache(queues)
        queue_names = sorted(queues.keys())
        self.stdout.write(f'Celery: {len(routes)} routes, {len(queue_names)} queues')

        from src.core.utils.celery_beat.manager import CeleryBeatModuleManager
        beat_manager = CeleryBeatModuleManager(use_config_cache=False)
        schedule = beat_manager.get_all_beat_schedules()
        self.stdout.write(f'Beat schedule: {len(schedule)} задач')

        elapsed = time.perf_counter() - start
        self.stdout.write(self.style.SUCCESS(f'Celery кэши прогреты ({elapsed:.2f}s)'))
