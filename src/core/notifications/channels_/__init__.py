"""
Реестр каналов доставки уведомлений.

Каналы — стратегии, реализующие интерфейс NotificationChannel.
На старте зарегистрирован один канал: in_app (запись в БД + push в WebSocket).
Будущие каналы (email, push, sms) добавляются регистрацией здесь, без
изменений в публичном API NotificationService и в модулях-источниках.
"""

from .base import NotificationChannel
from .in_app import InAppChannel

_REGISTRY: dict[str, NotificationChannel] = {
    'in_app': InAppChannel(),
}


def get_channels() -> dict[str, NotificationChannel]:
    return dict(_REGISTRY)


def register_channel(name: str, channel: NotificationChannel, *, override: bool = False) -> None:
    if not override and name in _REGISTRY:
        raise ValueError(f'Канал {name!r} уже зарегистрирован')
    _REGISTRY[name] = channel


__all__ = ['NotificationChannel', 'InAppChannel', 'get_channels', 'register_channel']
