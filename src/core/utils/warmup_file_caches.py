"""
Прогрев файловых кэшей без django.setup().

Контракт: celery_config.py / celery_beat_config.py модулей не должны
требовать django.setup() (только routes/queues/schedule и локальные классы).
"""

from __future__ import annotations

import logging
import time
from typing import Any

logger = logging.getLogger('core.utils.warmup')


def run_file_cache_warmup(*, include_modules_env: bool = True) -> dict[str, Any]:
    """
    Пересобирает discovered_apps, celery routes/queues, beat schedule
    и опционально modules_env. Не вызывает django.setup().
    """
    start = time.perf_counter()

    from src.core.utils.auto_api.discovered_apps_cache import get_discovered_apps

    apps = get_discovered_apps(use_cache=False)

    from src.core.utils.celery.manager import CeleryModuleManager
    from src.core.utils.celery_queues_cache import write_queues_cache

    manager = CeleryModuleManager(use_config_cache=False)
    routes = manager.get_all_task_routes()
    queues = manager.get_all_task_queues()
    write_queues_cache(queues)

    from src.core.utils.celery_beat.manager import CeleryBeatModuleManager

    beat_manager = CeleryBeatModuleManager(use_config_cache=False)
    schedule = beat_manager.get_all_beat_schedules()

    env_vars_count = 0
    if include_modules_env:
        from src.core.utils.environment.methods import collect_env_files_from_all_sources

        env_vars = collect_env_files_from_all_sources(use_cache=False)
        env_vars_count = len(env_vars) if env_vars else 0

    elapsed = time.perf_counter() - start
    result: dict[str, Any] = {
        'apps': len(apps),
        'routes': len(routes),
        'queues': len(queues),
        'beat_tasks': len(schedule),
        'modules_env': env_vars_count,
        'elapsed_sec': elapsed,
        'include_modules_env': include_modules_env,
    }
    logger.info(
        'Файловые кэши прогреты: apps=%s routes=%s queues=%s beat=%s env=%s (%.2fs)',
        result['apps'],
        result['routes'],
        result['queues'],
        result['beat_tasks'],
        result['modules_env'],
        elapsed,
    )
    return result
