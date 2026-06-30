"""Регистрация и доступ к реализации MediaClient."""

from typing import TYPE_CHECKING

from django.conf import settings

if TYPE_CHECKING:
    from src.core.utils.media_client.interface import MediaClient

_client: 'MediaClient | None' = None


def _create_client() -> 'MediaClient':
    mode = getattr(settings, 'MEDIA_ACCESS_MODE', 'local').strip().lower()
    if mode in ('remote', 'http'):
        from src.core.utils.media_client.remote import RemoteMediaClient
        return RemoteMediaClient()
    if mode == 'local':
        from src.core.utils.media_client.local import LocalMediaClient
        return LocalMediaClient()
    raise ValueError(f'Неизвестный MEDIA_ACCESS_MODE: {mode}')


def get_media_client() -> 'MediaClient':
    """Возвращает клиент media в зависимости от MEDIA_ACCESS_MODE."""
    global _client
    if _client is None:
        _client = _create_client()
    return _client


def reset_media_client(client: 'MediaClient | None' = None) -> None:
    """Сброс клиента (для тестов или смены настроек)."""
    global _client
    _client = client
