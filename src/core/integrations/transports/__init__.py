"""
Транспортный слой ModuleBridge.

Содержит интерфейсы Transport / EventBus и их реализации:
- LocalTransport / LocalEventBus — in-process (монолитный режим)
- HttpTransport — стаб для микросервисного режима (будущая фаза)
- CeleryEventBus — стаб для распределённой шины событий (будущая фаза)

Конкретная реализация выбирается фасадом bridge на основании Django settings
(BRIDGE_TRANSPORT, BRIDGE_EVENT_BUS).
"""

from .base import EventBus, Transport
from .local import LocalEventBus, LocalTransport

__all__ = [
    'EventBus',
    'Transport',
    'LocalEventBus',
    'LocalTransport',
]
