"""
Ускорение встроенного Django autoreload в development.

Работает, когда `commands dev` запущен напрямую. start_api.py вместо этого
запускает `dev --noreload` под scripts/dev_reloader.py.

- Игнор шумных путей (virtual_env, client, migrations, media, logs…):
  не триггерят reload и не участвуют в StatReloader.snapshot.
- Watchman (если установлены служба watchman и пакет pywatchman) Django
  выбирает сам; корневой .watchmanconfig дополнительно сужает дерево.
"""

from __future__ import annotations

import logging

from django.dispatch import receiver
from django.utils.autoreload import StatReloader, file_changed

from src.core.utils.autoreload_paths import should_ignore_autoreload_path

logger = logging.getLogger('core.utils.dev_autoreload')

_installed = False
_ORIGINAL_WATCHED_FILES = StatReloader.watched_files


@receiver(file_changed)
def _suppress_ignored_file_changed(sender, file_path, **kwargs):  # noqa: ARG001
    if should_ignore_autoreload_path(file_path):
        return True
    return None


def _filtered_watched_files(self, include_globs=True):
    for path in _ORIGINAL_WATCHED_FILES(self, include_globs=include_globs):
        if should_ignore_autoreload_path(path):
            continue
        yield path


def install_dev_autoreload_filters() -> None:
    """Подключает фильтры один раз (до запуска reloader parent/child)."""
    global _installed
    if _installed:
        return

    StatReloader.watched_files = _filtered_watched_files  # type: ignore[method-assign]
    _installed = True
    logger.info(
        'Autoreload: фильтры путей включены (virtual_env, client, migrations, media/logs)'
    )
