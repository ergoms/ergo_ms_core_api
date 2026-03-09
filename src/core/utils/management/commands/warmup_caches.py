"""
Прогрев файловых кэшей (discovered_apps, celery_routes_queues, celery_queues).

Выполняет полное discovery приложений и сборку конфигураций Celery,
записывая результаты в файловый кэш для быстрого старта worker/beat.
"""

import json
import logging
import time
from pathlib import Path

from django.core.management.base import BaseCommand

from src.config.settings.base import MODULES_DIR, VIRTUAL_ENV_DIR

logger = logging.getLogger('core.utils.commands')

CACHE_DIR = VIRTUAL_ENV_DIR / 'cache'
QUEUES_CACHE_FILE = CACHE_DIR / 'celery_queues.json'


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
    help = 'Прогрев файловых кэшей для быстрого старта Celery worker/beat'

    def handle(self, *args, **options):
        start = time.perf_counter()

        from src.core.utils.auto_api.discovered_apps_cache import get_discovered_apps
        apps = get_discovered_apps(use_cache=False)
        self.stdout.write(f'Discovered apps: {len(apps)}')

        from src.core.utils.celery.manager import CeleryModuleManager
        manager = CeleryModuleManager(use_config_cache=False)
        routes = manager.get_all_task_routes()
        queues = manager.get_all_task_queues()

        queue_names = sorted(queues.keys())
        CACHE_DIR.mkdir(parents=True, exist_ok=True)
        try:
            data = {
                'modules_mtime': _get_modules_config_mtime(),
                'queues': queue_names,
            }
            with open(QUEUES_CACHE_FILE, 'w', encoding='utf-8') as f:
                json.dump(data, f, indent=0)
        except OSError as e:
            logger.warning('Failed to write celery_queues.json: %s', e)

        elapsed = time.perf_counter() - start
        self.stdout.write(self.style.SUCCESS(
            f'Cache warmed: {len(routes)} routes, {len(queue_names)} queues ({elapsed:.2f}s)'
        ))
