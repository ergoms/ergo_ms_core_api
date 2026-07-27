"""
Ускорение Django autoreload в development.

- Игнор шумных путей (virtual_env, client, migrations, media, logs…):
  не триггерят reload и не участвуют в StatReloader.snapshot.
- Watchman (если установлены служба watchman и пакет pywatchman) Django
  выбирает сам; корневой .watchmanconfig дополнительно сужает дерево.
"""

from __future__ import annotations

import logging
from pathlib import Path, PurePosixPath

from django.dispatch import receiver
from django.utils.autoreload import StatReloader, file_changed

logger = logging.getLogger('core.utils.dev_autoreload')

_IGNORE_SUBSTRINGS = (
    '/virtual_env/',
    '/.git/',
    '/logs/',
    '/media/',
    '/__pycache__/',
    '/node_modules/',
    '/.cursor/',
    '/core/client/',
    '/core/media_api/',
)

_installed = False
_ORIGINAL_WATCHED_FILES = StatReloader.watched_files


def _normalize(path: Path | str) -> str:
    text = path.as_posix() if isinstance(path, Path) else str(path).replace('\\', '/')
    if not text.startswith('/'):
        text = f'/{text}'
    return text


def should_ignore_autoreload_path(path: Path | str) -> bool:
    """True — путь не должен вызывать reload / не нужно снимать mtime."""
    normalized = _normalize(path)
    lowered = normalized.lower()

    for segment in _IGNORE_SUBSTRINGS:
        if segment in lowered:
            return True

    parts = PurePosixPath(normalized).parts
    if 'migrations' in parts:
        return True

    # modules/<module>/client/… — UI модуля, не Python API
    if 'modules' in parts:
        try:
            idx = parts.index('modules')
        except ValueError:
            return False
        if 'client' in parts[idx + 1 :]:
            return True

    return False


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
