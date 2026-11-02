"""Регистрация и доступ к реализации MediaClient."""

from typing import TYPE_CHECKING

from django.conf import settings

if TYPE_CHECKING:
    from src.core.utils.media_client.interface import MediaClient

_client: 'MediaClient | None' = None


def _create_client() -> 'MediaClient':
    mode = getattr(settings, 'MEDIA_ACCESS_MODE', 'local').strip().lower()
    if mode == 'remote':
        from src.core.utils.media_client.remote import RemoteMediaClient
        inner = RemoteMediaClient()
    elif mode == 'local':
        from src.core.utils.media_client.local import LocalMediaClient
        inner = LocalMediaClient()
    else:
        raise ValueError(f'Неизвестный MEDIA_ACCESS_MODE: {mode}')
    from core.shared.media_zones import load_media_zones

    zones = load_media_zones()
    if not zones:
        return inner
    from src.core.utils.media_client.zoned import ZonedMediaClient
    return ZonedMediaClient(inner, zones)


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
