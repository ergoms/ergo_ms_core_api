"""Очереди Celery, которые принадлежат одному каталогу modules/<name>."""

from __future__ import annotations

from typing import Any


def queues_for_module(
    module_name: str,
    *,
    routes: dict[str, Any] | None = None,
) -> list[str]:
    """Имя модуля плюс очереди из маршрутов ``modules.<name>.*``.

    Worker ``--module=<name>`` слушает все эти очереди, а не только
    очередь с именем папки: у модуля могут быть вложенные Django-apps
    со своими ``queue`` в ``celery_config``.
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

    return sorted(owned)
