"""Локальный доступ к media через файловую систему (co-located с media_api)."""

import logging
import shutil
from pathlib import Path
from typing import BinaryIO

from django.conf import settings

from .path_utils import assert_within_root, normalize_media_path
from .pipeline import MediaPipelineMixin

logger = logging.getLogger(__name__)


class LocalMediaClient(MediaPipelineMixin):
    """Читает и пишет файлы напрямую в MEDIA_ROOT без HTTP."""

    def __init__(self, root_path: str | None = None):
        self._root = Path(root_path or settings.MEDIA_ROOT).resolve()
        self._root.mkdir(parents=True, exist_ok=True)

    @property
    def root_path(self) -> str:
        return str(self._root)

    def normalize_path(self, file_path: str) -> str:
        normalized = normalize_media_path(file_path)
        assert_within_root(normalized, self._root)
        return normalized

    def _resolve(self, path: str) -> Path:
        normalized = self.normalize_path(path)
        return (self._root / normalized).resolve()

    def exists(self, path: str) -> bool:
        try:
            return self._resolve(path).is_file()
        except ValueError:
            return False

    def open(self, path: str, mode: str = 'rb') -> BinaryIO:
        if 'w' in mode or 'a' in mode or '+' in mode:
            raise ValueError('LocalMediaClient.open поддерживает только чтение')
        return open(self._resolve(path), mode)

    def read_bytes(self, path: str) -> bytes:
        with self.open(path, 'rb') as file_obj:
            return file_obj.read()

    def save(self, path: str, content: BinaryIO | bytes) -> str:
        normalized = self.normalize_path(path)
        target = self._resolve(normalized)
        target.parent.mkdir(parents=True, exist_ok=True)

        if isinstance(content, (bytes, bytearray)):
            data = bytes(content)
        else:
            if hasattr(content, 'seek'):
                content.seek(0)
            data = content.read()

        with open(target, 'wb') as file_obj:
            file_obj.write(data)

        logger.debug('Файл сохранён локально: %s (%d байт)', normalized, len(data))
        return normalized

    def delete(self, path: str) -> bool:
        target = self._resolve(path)
        if target.is_file():
            target.unlink()
            return True
        return False

    def size(self, path: str) -> int:
        return self._resolve(path).stat().st_size

    def local_source_path(self, path: str) -> str | None:
        try:
            resolved = self._resolve(path)
        except ValueError:
            return None
        return str(resolved) if resolved.is_file() else None

    def commit_local(self, local_path: str, target: str) -> str:
        normalized = self.normalize_path(target)
        dest = self._resolve(normalized)
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(local_path, dest)
        logger.debug('commit_local: %s -> %s', local_path, normalized)
        return normalized
