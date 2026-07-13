"""
Сжатый вывод при старте Celery worker/beat.

Полные списки — при ERGO_CELERY_STARTUP_VERBOSE=true или флаге --verbose у ergoms start-worker/start-beat.
"""

from __future__ import annotations

import os
from typing import Iterable, Mapping, Optional, Sequence, Union

NamesInput = Union[Sequence[str], Iterable[str]]
LimitsInput = Mapping[str, int]

_TRUTHY = frozenset({'1', 'true', 'yes', 'on'})


def celery_startup_verbose() -> bool:
    """Полный вывод списков модулей/очередей при старте Celery."""
    return os.environ.get('ERGO_CELERY_STARTUP_VERBOSE', '').strip().lower() in _TRUTHY


def format_name_list(
    names: NamesInput,
    *,
    max_show: int = 3,
    verbose: Optional[bool] = None,
    empty_label: str = 'нет',
) -> str:
    """Сжимает длинный список имён: первые N + «… +K (всего M)»."""
    items = sorted(names)
    count = len(items)
    if count == 0:
        return empty_label
    show_full = verbose if verbose is not None else celery_startup_verbose()
    if show_full or count <= max_show:
        return ', '.join(items)
    head = ', '.join(items[:max_show])
    return f'{head}, … +{count - max_show} (всего {count})'


def format_limits_summary(
    limits: LimitsInput,
    *,
    max_show: int = 3,
    verbose: Optional[bool] = None,
) -> str:
    """Сжимает сводку лимитов параллелизма по очередям."""
    if not limits:
        return 'нет'
    pairs = [f'{queue}={limit}' for queue, limit in sorted(limits.items())]
    show_full = verbose if verbose is not None else celery_startup_verbose()
    if show_full or len(pairs) <= max_show:
        return ', '.join(pairs)
    head = ', '.join(pairs[:max_show])
    rest = len(pairs) - max_show
    return f'{head}, … +{rest} (всего {len(pairs)})'


def format_queues_display(
    queues: Optional[Sequence[str]],
    all_queues: Sequence[str],
    *,
    verbose: Optional[bool] = None,
) -> str:
    """Текст режима очередей для bootstrap-скриптов."""
    show_full = verbose if verbose is not None else celery_startup_verbose()
    if not queues:
        if all_queues:
            return f'все ({len(all_queues)})'
        return 'все'
    all_with_default = set(all_queues) | {'default'}
    if all_queues and set(queues) >= all_with_default:
        if show_full:
            return ','.join(queues)
        return f'все ({len(queues)})'
    if show_full or len(queues) <= 5:
        return ','.join(queues)
    return format_name_list(queues, max_show=3, verbose=False)
