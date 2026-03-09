"""
Кэш конфигурации Celery: маршруты/очереди и расписание Beat.

- celery_routes_queues.json — CeleryModuleManager (routes, queues)
- celery_beat_schedule.json — CeleryBeatModuleManager (schedule)
"""

import json
import logging
from pathlib import Path
from typing import Any, Dict, Optional, Tuple

from django.conf import settings

logger = logging.getLogger('celery.cache')

CACHE_DIR = Path(settings.VIRTUAL_ENV_DIR) / 'cache'
CACHE_FILE = CACHE_DIR / 'celery_routes_queues.json'
BEAT_SCHEDULE_CACHE_FILE = CACHE_DIR / 'celery_beat_schedule.json'


def _get_fingerprint() -> Dict[str, float]:
    """Fingerprint на основе mtime конфигурационных файлов модулей."""
    project_root = Path(settings.SYSTEM_DIR)
    modules_dir = Path(settings.MODULES_DIR)
    result: Dict[str, float] = {}
    if modules_dir.exists():
        result['modules'] = modules_dir.stat().st_mtime
        for module_dir in sorted(modules_dir.iterdir()):
            if not module_dir.is_dir():
                continue
            for cfg_name in ('celery_config.py', 'celery_beat_config.py'):
                cfg = module_dir / cfg_name
                if cfg.exists():
                    key = str(cfg.relative_to(project_root))
                    result[key] = cfg.stat().st_mtime
            api_cfg = module_dir / 'api' / 'celery_config.py'
            if api_cfg.exists():
                key = str(api_cfg.relative_to(project_root))
                result[key] = api_cfg.stat().st_mtime
    core_path = project_root / 'core'
    if core_path.exists():
        result['core'] = core_path.stat().st_mtime
    return result


def write_routes_queues_cache(
    routes: Dict[str, Any],
    queues: Dict[str, Any],
) -> None:
    """Сохраняет маршруты и очереди в файловый кэш с fingerprint."""
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    data = {
        'fingerprint': _get_fingerprint(),
        'routes': routes,
        'queues': queues,
    }
    try:
        with open(CACHE_FILE, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=0)
        logger.debug(
            'celery_routes_queues.json: записано %d маршрутов, %d очередей',
            len(routes), len(queues),
        )
    except OSError as e:
        logger.warning('Не удалось записать celery_routes_queues.json: %s', e)


def read_routes_queues_cache() -> Optional[Tuple[Dict[str, Any], Dict[str, Any]]]:
    """
    Читает routes и queues из кэша.
    Возвращает (routes, queues) или None если кэш невалиден.
    """
    if not CACHE_FILE.exists():
        return None
    try:
        with open(CACHE_FILE, 'r', encoding='utf-8') as f:
            data = json.load(f)
        if data.get('fingerprint') != _get_fingerprint():
            return None
        routes = data.get('routes')
        queues = data.get('queues')
        if routes is not None and queues is not None:
            return (routes, queues)
    except (json.JSONDecodeError, KeyError, OSError):
        pass
    return None


def write_beat_schedule_cache(schedule: Dict[str, Dict[str, Any]]) -> None:
    """Сохраняет расписание Beat в файловый кэш с fingerprint."""
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    data = {
        'fingerprint': _get_fingerprint(),
        'schedule': schedule,
    }
    try:
        with open(BEAT_SCHEDULE_CACHE_FILE, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=0)
        logger.debug('celery_beat_schedule.json: записано %d задач', len(schedule))
    except OSError as e:
        logger.warning('Не удалось записать celery_beat_schedule.json: %s', e)


def read_beat_schedule_cache() -> Optional[Dict[str, Dict[str, Any]]]:
    """
    Читает расписание Beat из кэша.
    Возвращает schedule или None если кэш невалиден.
    """
    if not BEAT_SCHEDULE_CACHE_FILE.exists():
        return None
    try:
        with open(BEAT_SCHEDULE_CACHE_FILE, 'r', encoding='utf-8') as f:
            data = json.load(f)
        if data.get('fingerprint') != _get_fingerprint():
            return None
        schedule = data.get('schedule')
        if schedule is not None:
            return schedule
    except (json.JSONDecodeError, KeyError, OSError):
        pass
    return None
