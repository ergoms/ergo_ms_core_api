"""
Прогрев всех файловых кэшей:
- discovered_apps, celery_routes_queues, celery_queues
- celery_beat_schedule
- modules_env
"""
import logging
import time

from django.core.management.base import BaseCommand

from src.config.settings.base import MODULES_DIR

logger = logging.getLogger('core.utils.commands')


def _get_modules_config_mtime() -> float:
    """Вычисляет max mtime конфигов Celery модулей."""
    max_mtime = 0.0
    if not MODULES_DIR.exists():
        return max_mtime
    max_mtime = MODULES_DIR.stat().st_mtime
    for module_dir in MODULES_DIR.iterdir():
        if not module_dir.is_dir():
            continue
        for cfg_name in ('celery_config.py', 'celery_beat_config.py'):
            cfg = module_dir / cfg_name
            if cfg.exists():
                max_mtime = max(max_mtime, cfg.stat().st_mtime)
        api_cfg = module_dir / 'api' / 'celery_config.py'
        if api_cfg.exists():
            max_mtime = max(max_mtime, api_cfg.stat().st_mtime)
    return max_mtime


class Command(BaseCommand):
    help = 'Прогрев всех файловых кэшей для быстрого старта API, Celery worker и Beat'

    def handle(self, *args, **options):
        start = time.perf_counter()

        from src.core.utils.auto_api.discovered_apps_cache import get_discovered_apps
        apps = get_discovered_apps(use_cache=False)
        self.stdout.write(f'Обнаружено приложений: {len(apps)}')

        from src.core.utils.celery.manager import CeleryModuleManager
        from src.core.utils.celery_queues_cache import write_queues_cache

        manager = CeleryModuleManager(use_config_cache=False)
        routes = manager.get_all_task_routes()
        queues = manager.get_all_task_queues()

        write_queues_cache(queues)
        queue_names = sorted(queues.keys())
        self.stdout.write(f'Celery: {len(routes)} маршрутов, {len(queue_names)} очередей')

        from src.core.utils.celery_beat.manager import CeleryBeatModuleManager
        beat_manager = CeleryBeatModuleManager(use_config_cache=False)
        schedule = beat_manager.get_all_beat_schedules()
        self.stdout.write(f'Расписание Beat: {len(schedule)} задач')

        from src.core.utils.environment.methods import collect_env_files_from_all_sources
        env_vars = collect_env_files_from_all_sources(use_cache=False)
        if env_vars:
            self.stdout.write(f'Переменные модулей: {len(env_vars)}')

        elapsed = time.perf_counter() - start
        self.stdout.write(self.style.SUCCESS(f'Все кэши прогреты ({elapsed:.2f}s)'))
