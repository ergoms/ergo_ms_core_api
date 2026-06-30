"""Контракт compute-пайплайна поверх MediaClient: localize / commit_local.

Позволяет модулям (видео, документы, FAISS) работать с настоящими локальными
путями для ffmpeg/faiss/парсеров, не привязываясь к режиму доступа:

    client = get_media_client()
    src = client.localize(video.file.name)        # local: тот же файл; remote: скачано в cache
    run_ffmpeg(src.path, out_path)                 # нативный путь в обоих режимах
    client.commit_local(out_path, 'video_analysis/results/x.mp4')
    if src.cached:
        src.release()                              # удалить кэш-копию (опционально)
"""

import hashlib
import logging
import os
from dataclasses import dataclass
from pathlib import Path

from django.conf import settings

logger = logging.getLogger(__name__)


@dataclass
class LocalizedFile:
    """Локальный путь к файлу canonical-хранилища для нативной обработки."""

    path: str
    cached: bool  # True — копия в cache (remote); False — прямой файл MEDIA_ROOT

    def __fspath__(self) -> str:
        return self.path

    def __str__(self) -> str:
        return self.path

    def release(self) -> None:
        """Удалить кэш-копию (только если это cached-файл из remote-режима)."""
        if not self.cached:
            return
        try:
            os.remove(self.path)
        except OSError:
            pass


class MediaPipelineMixin:
    """Добавляет localize()/commit_local() к MediaClient (DRY между local и remote).

    Клиенты переопределяют точечные хуки:
    - local_source_path() — прямой путь без копирования (local-режим);
    - download_to() — потоковая загрузка в cache (remote-режим);
    - commit_local() — потоковая запись результата.
    """

    def local_source_path(self, path: str) -> str | None:
        """Реальный путь к файлу без копирования, если доступен. Иначе None."""
        return None

    def download_to(self, path: str, dest: str) -> None:
        """Скачать файл хранилища в локальный dest. По умолчанию через read_bytes."""
        data = self.read_bytes(path)  # type: ignore[attr-defined]
        with open(dest, 'wb') as file_obj:
            file_obj.write(data)

    def localize(self, path: str) -> LocalizedFile:
        """Вернуть локальный путь к файлу хранилища для нативной обработки."""
        normalized = self.normalize_path(path)  # type: ignore[attr-defined]

        direct = self.local_source_path(normalized)
        if direct is not None:
            return LocalizedFile(path=direct, cached=False)

        try:
            size = self.size(normalized)  # type: ignore[attr-defined]
        except Exception:
            size = -1

        cache_root = Path(settings.MEDIA_CACHE_ROOT).resolve()
        key = hashlib.sha256(f'{normalized}:{size}'.encode('utf-8')).hexdigest()[:32]
        dest = cache_root / key / Path(normalized).name

        if dest.is_file() and size >= 0 and dest.stat().st_size == size:
            logger.debug('localize: cache hit %s', normalized)
            return LocalizedFile(path=str(dest), cached=True)

        dest.parent.mkdir(parents=True, exist_ok=True)
        tmp = dest.with_name(dest.name + '.part')
        self.download_to(normalized, str(tmp))
        os.replace(tmp, dest)
        logger.debug('localize: cached %s (%d байт)', normalized, dest.stat().st_size)
        return LocalizedFile(path=str(dest), cached=True)

    def commit_local(self, local_path: str, target: str) -> str:
        """Залить локальный файл-результат в canonical-хранилище. По умолчанию через save."""
        with open(local_path, 'rb') as file_obj:
            return self.save(target, file_obj)  # type: ignore[attr-defined]
