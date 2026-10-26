"""Учёт запуска источников на экране мониторинга.

Namespace и source_id задаёт модуль. Имён установленных модулей здесь нет.
"""

from .runs import (
    attach,
    claim,
    claimed_ids,
    is_claimed,
    prune_finished,
    reconcile,
    release,
    revoke_attached,
    task_ids as claimed_task_ids,
)
from .snapshot import (
    bump_source_status,
    read_snapshot,
    serve_snapshot,
    shell_sources,
    store_snapshot,
)

__all__ = [
    'attach',
    'bump_source_status',
    'claim',
    'claimed_ids',
    'claimed_task_ids',
    'is_claimed',
    'prune_finished',
    'read_snapshot',
    'reconcile',
    'release',
    'revoke_attached',
    'serve_snapshot',
    'shell_sources',
    'store_snapshot',
]
