"""
Точка входа для Celery (-A src) без загрузки celery при импорте подпакетов src.*.
"""

from __future__ import annotations

from typing import Any

__all__ = ('celery_app', 'celery')


def __getattr__(name: str) -> Any:
    if name in ('celery_app', 'celery'):
        from src.config.celery import celery_app as app

        return app
    raise AttributeError(f'module {__name__!r} has no attribute {name!r}')
