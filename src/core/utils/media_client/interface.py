"""Протокол доступа к media-хранилищу из core/api."""

from typing import BinaryIO, Protocol

from .pipeline import LocalizedFile


class MediaClient(Protocol):
    """Абстракция доступа к файлам: локальная ФС или HTTP к media_api."""

    @property
    def root_path(self) -> str:
        """Корень хранилища (абсолютный путь в local, логический в remote)."""
        ...

    def normalize_path(self, file_path: str) -> str:
        """Нормализует и валидирует относительный путь."""
        ...

    def exists(self, path: str) -> bool:
        ...

    def open(self, path: str, mode: str = 'rb') -> BinaryIO:
        ...

    def read_bytes(self, path: str) -> bytes:
        ...

    def save(self, path: str, content: BinaryIO | bytes) -> str:
        ...

    def delete(self, path: str) -> bool:
        ...

    def size(self, path: str) -> int:
        ...

    # --- Compute-пайплайн (см. pipeline.MediaPipelineMixin) ---

    def localize(self, path: str) -> LocalizedFile:
        """Вернуть локальный путь к файлу для нативной обработки (ffmpeg/faiss/парсер)."""
        ...

    def commit_local(self, local_path: str, target: str) -> str:
        """Залить локальный файл-результат в canonical-хранилище. Вернуть storage-путь."""
        ...
