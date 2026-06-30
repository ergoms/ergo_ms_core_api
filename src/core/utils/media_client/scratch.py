"""Эфемерное локальное хранилище для compute-пайплайнов.

Scratch — это временные файлы обработки (staging перед Celery, промежуточные
кадры, распакованные документы). Они НИКОГДА не попадают в БД и не раздаются
через signed URL. Всегда локальны на машине воркера и удаляются после задачи.
"""

import logging
import shutil
import uuid
from contextlib import contextmanager
from pathlib import Path

from django.conf import settings

logger = logging.getLogger(__name__)


class ScratchStore:
    """Управляет временными каталогами/файлами compute-пайплайна."""

    def __init__(self, root: str | None = None):
        self._root = Path(root or settings.MEDIA_SCRATCH_ROOT).resolve()
        self._root.mkdir(parents=True, exist_ok=True)

    @property
    def root(self) -> Path:
        return self._root

    def new_dir(self, prefix: str = 'job') -> Path:
        """Создать уникальный временный каталог."""
        path = self._root / f'{prefix}_{uuid.uuid4().hex}'
        path.mkdir(parents=True, exist_ok=True)
        return path

    def new_path(self, suffix: str = '', prefix: str = 'tmp') -> Path:
        """Вернуть уникальный путь под временный файл (без создания)."""
        return self._root / f'{prefix}_{uuid.uuid4().hex}{suffix}'

    def cleanup(self, path: str | Path) -> None:
        """Удалить временный файл/каталог. Игнорирует пути вне scratch-корня."""
        try:
            target = Path(path).resolve()
        except (OSError, ValueError):
            return
        root = str(self._root)
        if target != self._root and not str(target).startswith(root):
            logger.warning('ScratchStore.cleanup: путь вне scratch-корня: %s', path)
            return
        try:
            if target.is_dir():
                shutil.rmtree(target, ignore_errors=True)
            elif target.exists():
                target.unlink()
        except OSError as exc:
            logger.warning('ScratchStore.cleanup ошибка для %s: %s', path, exc)

    @contextmanager
    def session(self, prefix: str = 'job'):
        """Контекст с авто-очисткой каталога после обработки."""
        path = self.new_dir(prefix)
        try:
            yield path
        finally:
            self.cleanup(path)


_store: 'ScratchStore | None' = None


def get_scratch_store() -> ScratchStore:
    global _store
    if _store is None:
        _store = ScratchStore()
    return _store


def reset_scratch_store(store: 'ScratchStore | None' = None) -> None:
    global _store
    _store = store
