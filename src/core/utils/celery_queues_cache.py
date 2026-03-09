"""
Кэш списка Celery-очередей (celery_queues.bin).

Записывается при warmup_caches, читается скриптами запуска (start_celery_worker.py)
без загрузки Django для минимального времени старта.
"""
import logging
from pathlib import Path
from typing import Any, Dict, List

from django.conf import settings

logger = logging.getLogger('celery.cache')

CACHE_DIR = Path(settings.VIRTUAL_ENV_DIR) / 'cache'
CACHE_FILE = CACHE_DIR / 'celery_queues.bin'


def _get_modules_config_mtime() -> float:
    """Max mtime по celery_config.py / celery_beat_config.py модулей."""
    modules_dir = Path(settings.MODULES_DIR)
    max_mtime = 0.0
    if modules_dir.exists():
        max_mtime = modules_dir.stat().st_mtime
        for module_dir in modules_dir.iterdir():
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


def write_queues_cache(queues: Dict[str, Any]) -> None:
    """Записывает список очередей и mtime для валидации скриптами запуска."""
    from src.core.utils.cache_io import write_bin_cache

    queue_names = sorted(queues.keys()) if queues else []
    data = {
        'queues': queue_names,
        'modules_mtime': _get_modules_config_mtime(),
    }
    if write_bin_cache(CACHE_FILE, data):
        logger.debug('celery_queues.bin: записано %d очередей', len(queue_names))


def read_queues_cache() -> List[str]:
    """Читает список очередей из кэша (для использования в Django-контексте)."""
    from src.core.utils.cache_io import read_bin_cache

    data = read_bin_cache(CACHE_FILE)
    if data is None:
        return []
    stored_mtime = data.get('modules_mtime', 0)
    current_mtime = _get_modules_config_mtime()
    if stored_mtime >= current_mtime:
        return data.get('queues', [])
    return []
