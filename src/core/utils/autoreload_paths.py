"""
Какие файлы следует отслеживать при горячей перезагрузке API в development.

Только стандартная библиотека: модуль импортирует и Django-фильтр StatReloader,
и лёгкий наблюдатель scripts/dev_reloader.py, который работает без Django.
"""

from __future__ import annotations

import os
from collections.abc import Iterator
from pathlib import Path, PurePosixPath

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

# Каталоги, в которые обход не спускается: в них нет серверного Python.
_SKIP_DIR_NAMES = frozenset({
    '__pycache__',
    'node_modules',
    'migrations',
    'media',
    'logs',
    'client',
    'virtual_env',
})


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
        idx = parts.index('modules')
        if 'client' in parts[idx + 1 :]:
            return True

    return False


def dev_watch_roots(project_root: Path) -> list[Path]:
    """
    Каталоги серверного кода: ядро и modules/<name>/api.

    Из модулей API импортирует только пакет api, поэтому правка tools/ или
    data/ модуля сервер не перезапускает.
    """
    roots = [project_root / 'core' / 'api' / 'src']
    modules_dir = project_root / 'modules'
    if modules_dir.is_dir():
        for entry in sorted(modules_dir.iterdir()):
            api_dir = entry / 'api'
            if api_dir.is_dir():
                roots.append(api_dir)
    return roots


def snapshot_dev_watch_files(roots: list[Path]) -> dict[str, int]:
    """{путь .py: mtime_ns}. На Windows mtime берётся из листинга каталога без stat на файл."""
    return dict(_iter_py_mtimes(roots))


def _iter_py_mtimes(roots: list[Path]) -> Iterator[tuple[str, int]]:
    stack = [str(root) for root in roots]
    while stack:
        current = stack.pop()
        try:
            entries = os.scandir(current)
        except OSError:
            continue
        with entries:
            for entry in entries:
                name = entry.name
                try:
                    is_dir = entry.is_dir(follow_symlinks=False)
                except OSError:
                    continue
                if is_dir:
                    if name.startswith('.') or name in _SKIP_DIR_NAMES:
                        continue
                    stack.append(entry.path)
                elif name.endswith('.py'):
                    try:
                        yield entry.path, entry.stat(follow_symlinks=False).st_mtime_ns
                    except OSError:
                        continue
