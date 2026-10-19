"""Очереди Celery, которые принадлежат одному каталогу modules/<name>."""

from __future__ import annotations

import ast
import logging
from pathlib import Path
from typing import Any, Iterable

logger = logging.getLogger('celery.module_queues')

_QUEUE_KEY = 'queue'
DEDICATED_QUEUES_FILENAME = 'dedicated_queues.yaml'
MODULE_WORKERS_FILENAME = 'celery_workers.yaml'


def _project_root() -> Path:
    # core/api/src/core/utils/celery/module_queues.py → корень рядом с modules/
    return Path(__file__).resolve().parents[6]


def _default_module_dir(module_name: str) -> Path:
    return _project_root() / 'modules' / module_name


def _literal_str(node: ast.AST | None) -> str | None:
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        value = node.value.strip()
        return value or None
    return None


def _queues_from_assign_target(node: ast.AST) -> Iterable[str]:
    if isinstance(node, ast.Dict):
        yield from _queues_from_dict(node)
        return
    if isinstance(node, (ast.List, ast.Tuple, ast.Set)):
        for elt in node.elts:
            yield from _queues_from_assign_target(elt)


def _queues_from_dict(node: ast.Dict) -> Iterable[str]:
    for key, value in zip(node.keys, node.values):
        if _literal_str(key) == _QUEUE_KEY:
            queue = _literal_str(value)
            if queue:
                yield queue
        if isinstance(value, ast.Dict):
            yield from _queues_from_dict(value)
        elif isinstance(value, (ast.List, ast.Tuple, ast.Set)):
            for elt in value.elts:
                yield from _queues_from_assign_target(elt)


def queues_from_celery_configs(module_dir: Path) -> set[str]:
    """Имена очередей из ``celery_config.py`` каталога модуля, без импорта Django."""
    found: set[str] = set()
    if not module_dir.is_dir():
        return found
    for path in module_dir.rglob('celery_config.py'):
        try:
            source = path.read_text(encoding='utf-8')
            tree = ast.parse(source, filename=str(path))
        except (OSError, SyntaxError) as exc:
            logger.debug('Не удалось разобрать %s: %s', path, exc)
            continue
        for node in ast.walk(tree):
            if isinstance(node, ast.Dict):
                found.update(_queues_from_dict(node))
    return found


def queues_for_module(
    module_name: str,
    *,
    routes: dict[str, Any] | None = None,
    module_dir: str | Path | None = None,
) -> list[str]:
    """Имя модуля плюс очереди из маршрутов ``modules.<name>.*``.

    Worker ``--module=<name>`` слушает все эти очереди, а не только
    очередь с именем папки: у модуля могут быть вложенные Django-apps
    со своими ``queue`` в ``celery_config``.

    Пустой кэш routes не обнуляет набор: очереди дополнительно читаются
    из файлов ``celery_config.py`` каталога модуля.
    """
    catalog = (module_name or '').strip()
    if not catalog:
        return []

    owned: set[str] = {catalog}
    prefix = f'modules.{catalog}.'
    for pattern, dest in (routes or {}).items():
        if not isinstance(pattern, str) or not pattern.startswith(prefix):
            continue
        queue = dest.get('queue') if isinstance(dest, dict) else dest
        if isinstance(queue, str) and queue.strip():
            owned.add(queue.strip())

    directory = Path(module_dir) if module_dir is not None else _default_module_dir(catalog)
    owned.update(queues_from_celery_configs(directory))

    return sorted(owned)


def _load_yaml_mapping(path: Path) -> dict[str, Any]:
    if not path.is_file():
        return {}
    try:
        import yaml
    except ImportError:
        logger.debug('PyYAML недоступен, %s пропущен', path)
        return {}
    try:
        data = yaml.safe_load(path.read_text(encoding='utf-8')) or {}
    except (OSError, yaml.YAMLError) as exc:
        logger.debug('Не удалось прочитать %s: %s', path, exc)
        return {}
    return data if isinstance(data, dict) else {}


def _positive_int(raw: Any) -> int | None:
    if raw is None or raw == '':
        return None
    try:
        value = int(raw)
    except (TypeError, ValueError):
        return None
    return value if value > 0 else None


def _concurrency(raw: Any) -> int:
    try:
        value = int(raw or 1)
    except (TypeError, ValueError):
        value = 1
    return max(1, value)


def _queue_list(raw: Any, fallback: str) -> list[str]:
    if isinstance(raw, str):
        names = [part.strip() for part in raw.split(',') if part.strip()]
        return names or ([fallback] if fallback else [])
    if isinstance(raw, list):
        names = [str(item).strip() for item in raw if str(item).strip()]
        return names or ([fallback] if fallback else [])
    return [fallback] if fallback else []


def _worker_spec(item: Any, *, queues_from_name: bool) -> dict[str, Any] | None:
    if not isinstance(item, dict):
        return None
    name = str(item.get('name') or '').strip()
    hostname = str(item.get('hostname') or '').strip()
    if not name or not hostname:
        return None
    if queues_from_name:
        queues = [name]
    else:
        queues = _queue_list(item.get('queues'), name)
    if not queues:
        return None
    spec = {
        'name': name,
        'hostname': hostname,
        'queues': queues,
        'concurrency': _concurrency(item.get('concurrency')),
    }
    pool = str(item.get('pool') or '').strip().lower()
    if pool:
        spec['pool'] = pool
    tasks_limit = _positive_int(item.get('max_tasks_per_child'))
    memory_mb = _positive_int(item.get('max_memory_per_child_mb'))
    memory_kb = _positive_int(item.get('max_memory_per_child'))
    if memory_mb:
        memory_kb = memory_mb * 1024
    if tasks_limit:
        spec['max_tasks_per_child'] = tasks_limit
    if memory_kb:
        spec['max_memory_per_child'] = memory_kb
    return spec


def read_dedicated_queues(module_dir: str | Path) -> list[dict[str, Any]]:
    """Старый hook ``dedicated_queues.yaml``: одна очередь — один процесс.

    Поле ``name`` одновременно имя очереди. Новый hook — ``celery_workers.yaml``.
    """
    data = _load_yaml_mapping(Path(module_dir) / DEDICATED_QUEUES_FILENAME)
    raw = data.get('queues')
    if not isinstance(raw, list):
        return []
    specs: list[dict[str, Any]] = []
    for item in raw:
        spec = _worker_spec(item, queues_from_name=True)
        if spec is None:
            continue
        specs.append({
            'name': spec['name'],
            'hostname': spec['hostname'],
            'concurrency': spec['concurrency'],
        })
    return specs


def read_module_workers(module_dir: str | Path) -> list[dict[str, Any]]:
    """Именованные воркеры модуля.

    ``celery_workers.yaml`` задаёт id, hostname и список очередей.
    Записи ``dedicated_queues.yaml`` дополняют список, если id ещё нет:
    там ``name`` — и очередь, и id воркера.
    """
    directory = Path(module_dir)
    by_name: dict[str, dict[str, Any]] = {}
    order: list[str] = []

    def _add(spec: dict[str, Any] | None) -> None:
        if spec is None or spec['name'] in by_name:
            return
        by_name[spec['name']] = spec
        order.append(spec['name'])

    workers = _load_yaml_mapping(directory / MODULE_WORKERS_FILENAME).get('workers')
    if isinstance(workers, list):
        for item in workers:
            _add(_worker_spec(item, queues_from_name=False))

    for legacy in read_dedicated_queues(directory):
        _add(_worker_spec(
            {
                'name': legacy['name'],
                'hostname': legacy['hostname'],
                'concurrency': legacy['concurrency'],
                'queues': [legacy['name']],
            },
            queues_from_name=False,
        ))
    return [by_name[name] for name in order]


def module_worker_queue_names(module_dir: str | Path) -> set[str]:
    """Очереди, которые слушает именованный воркер, а не общий worker модуля."""
    names: set[str] = set()
    for spec in read_module_workers(module_dir):
        names.update(spec['queues'])
    return names


def find_module_worker(module_dir: str | Path, worker_name: str) -> dict[str, Any] | None:
    wanted = (worker_name or '').strip()
    if not wanted:
        return None
    for spec in read_module_workers(module_dir):
        if spec['name'] == wanted:
            return spec
    return None


def dedicated_queue_names(modules_root: str | Path) -> set[str]:
    """Очереди именованных воркеров всех каталогов modules/<name>/."""
    root = Path(modules_root)
    names: set[str] = set()
    if not root.is_dir():
        return names
    for path in root.iterdir():
        if path.is_dir():
            names.update(module_worker_queue_names(path))
    return names
