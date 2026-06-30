"""Нормализация и проверка путей внутри media-хранилища."""

import os
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from pathlib import Path


def normalize_media_path(file_path: str) -> str:
    """
    Нормализует относительный путь к файлу в формате storage (слэши /).
    Запрещает path traversal и абсолютные пути.
    """
    if not isinstance(file_path, str) or not file_path.strip():
        raise ValueError('Недопустимое значение пути к файлу')

    normalized = os.path.normpath(file_path.replace('\\', '/').lstrip('/'))
    if normalized in ('', '.', '..') or normalized.startswith('..'):
        raise ValueError('Недопустимый путь к файлу')
    if os.path.isabs(normalized):
        raise ValueError('Недопустимый путь к файлу')

    return normalized.replace(os.sep, '/')


def assert_within_root(normalized_path: str, root: 'Path | str') -> None:
    """Проверяет, что путь не выходит за пределы корня хранилища (локальный режим)."""
    root_path = os.path.realpath(str(root))
    resolved = os.path.realpath(os.path.join(root_path, normalized_path))
    if resolved != root_path and not resolved.startswith(root_path + os.sep):
        raise ValueError('Недопустимый путь к файлу')
