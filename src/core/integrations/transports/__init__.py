"""
Транспортный слой ModuleBridge.

Интерфейсы Transport / EventBus и in-process реализации
LocalTransport / LocalEventBus (монолитный режим).
"""

from .base import EventBus, Transport
from .local import LocalEventBus, LocalTransport

__all__ = [
    'EventBus',
    'Transport',
    'LocalEventBus',
    'LocalTransport',
]
