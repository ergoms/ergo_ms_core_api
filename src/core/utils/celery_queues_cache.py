"""
Кэш списка Celery-очередей (celery_queues.json).

Записывается при warmup_caches, читается скриптами запуска (start_celery_worker.py)
без загрузки Django для минимального времени старта.
"""

import json
import logging
from pathlib import Path
from typing import Any, Dict, List

from django.conf import settings

logger = logging.getLogger('celery.cache')

CACHE_DIR = Path(settings.VIRTUAL_ENV_DIR) / 'cache'
CACHE_FILE = CACHE_DIR / 'celery_queues.json'


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
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    queue_names = sorted(queues.keys()) if queues else []
    data = {
        'queues': queue_names,
        'modules_mtime': _get_modules_config_mtime(),
    }
    try:
        with open(CACHE_FILE, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=0)
        logger.debug('celery_queues.json: записано %d очередей', len(queue_names))
    except OSError as e:
        logger.warning('Не удалось записать celery_queues.json: %s', e)


def read_queues_cache() -> List[str]:
    """Читает список очередей из кэша (для использования в Django-контексте)."""
    if not CACHE_FILE.exists():
        return []
    try:
        with open(CACHE_FILE, 'r', encoding='utf-8') as f:
            data = json.load(f)
        stored_mtime = data.get('modules_mtime', 0)
        current_mtime = _get_modules_config_mtime()
        if stored_mtime >= current_mtime:
            return data.get('queues', [])
    except (json.JSONDecodeError, KeyError, OSError):
        pass
    return []
