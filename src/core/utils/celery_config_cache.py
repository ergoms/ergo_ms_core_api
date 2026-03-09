"""
Кэш конфигурации Celery: маршруты/очереди и расписание Beat.

- celery_routes_queues.json — CeleryModuleManager (routes, queues)
- celery_beat_schedule.json — CeleryBeatModuleManager (schedule)
"""

import json
import logging
from datetime import timedelta
from pathlib import Path
from typing import Any, Dict, Optional, Tuple

from django.conf import settings

logger = logging.getLogger('celery.cache')

_SCHEDULE_TYPE = '_schedule_type'


def _to_json_safe(val: Any) -> Any:
    """Преобразует значение в JSON-совместимый тип."""
    if isinstance(val, (set, frozenset)):
        return sorted(val)
    return val


def _serialize_schedule_value(obj: Any) -> Any:
    """Сериализует объект расписания Celery в JSON-совместимый dict."""
    from celery.schedules import crontab, schedule

    if isinstance(obj, crontab):
        return {
            _SCHEDULE_TYPE: 'crontab',
            'minute': _to_json_safe(getattr(obj, '_orig_minute', '*')),
            'hour': _to_json_safe(getattr(obj, '_orig_hour', '*')),
            'day_of_week': _to_json_safe(getattr(obj, '_orig_day_of_week', '*')),
            'day_of_month': _to_json_safe(getattr(obj, '_orig_day_of_month', '*')),
            'month_of_year': _to_json_safe(getattr(obj, '_orig_month_of_year', '*')),
        }
    if isinstance(obj, schedule):
        run_every = getattr(obj, 'run_every', None)
        sec = run_every.total_seconds() if run_every else 0
        return {
            _SCHEDULE_TYPE: 'schedule',
            'run_every': sec,
            'relative': getattr(obj, 'relative', False),
        }
    if isinstance(obj, timedelta):
        return {_SCHEDULE_TYPE: 'timedelta', 'seconds': obj.total_seconds()}
    return obj


def _deserialize_schedule_value(data: Any) -> Any:
    """Восстанавливает объект расписания Celery из dict."""
    from celery.schedules import crontab, schedule

    if not isinstance(data, dict) or _SCHEDULE_TYPE not in data:
        return data
    stype = data[_SCHEDULE_TYPE]
    if stype == 'crontab':
        return crontab(
            minute=data.get('minute', '*'),
            hour=data.get('hour', '*'),
            day_of_week=data.get('day_of_week', '*'),
            day_of_month=data.get('day_of_month', '*'),
            month_of_year=data.get('month_of_year', '*'),
        )
    if stype == 'schedule':
        sec = data.get('run_every', 0)
        return schedule(run_every=timedelta(seconds=sec), relative=data.get('relative', False))
    if stype == 'timedelta':
        return timedelta(seconds=data.get('seconds', 0))
    return data


def _serialize_schedule(schedule_dict: Dict[str, Dict[str, Any]]) -> Dict[str, Dict[str, Any]]:
    """Сериализует весь schedule: преобразует все schedule-значения в JSON-совместимые."""
    result = {}
    for name, entry in schedule_dict.items():
        serialized = {}
        for k, v in entry.items():
            serialized[k] = _serialize_schedule_value(v)
        result[name] = serialized
    return result


def _deserialize_schedule(data: Dict[str, Dict[str, Any]]) -> Dict[str, Dict[str, Any]]:
    """Восстанавливает schedule: преобразует dict обратно в объекты Celery."""
    result = {}
    for name, entry in data.items():
        restored = {}
        for k, v in entry.items():
            restored[k] = _deserialize_schedule_value(v)
        result[name] = restored
    return result

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
    serialized = _serialize_schedule(schedule)
    data = {
        'fingerprint': _get_fingerprint(),
        'schedule': serialized,
    }
    try:
        with open(BEAT_SCHEDULE_CACHE_FILE, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=2)
        logger.debug('celery_beat_schedule.json: записано %d задач', len(schedule))
    except (OSError, TypeError) as e:
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
            return _deserialize_schedule(schedule)
    except (json.JSONDecodeError, KeyError, OSError):
        pass
    return None
