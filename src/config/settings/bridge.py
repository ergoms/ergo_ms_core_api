"""
Настройки ModuleBridge — единого механизма межмодульного взаимодействия.

В монолитном режиме используются in-process реализации
``LocalTransport`` / ``LocalEventBus`` — никаких внешних зависимостей.

Поддерживается только ``local``. Значения ``BRIDGE_TRANSPORT`` /
``BRIDGE_EVENT_BUS`` отличны от ``local`` приводят к ``ImproperlyConfigured``
на старте (удалённые транспорты не реализованы).

``BRIDGE_ISOLATION`` управляет runtime-стражем изоляции модулей
(см. ``src/core/integrations/isolation.py``):

    BRIDGE_ISOLATION=off     # хук не устанавливается
    BRIDGE_ISOLATION=warn    # warnings.warn + лог (по умолчанию)
    BRIDGE_ISOLATION=raise   # BridgeIsolationError при нарушении (для CI/тестов)
"""

from src.config.env import env

BRIDGE_TRANSPORT = env.str('BRIDGE_TRANSPORT', default='local').strip().lower()
BRIDGE_EVENT_BUS = env.str('BRIDGE_EVENT_BUS', default='local').strip().lower()

BRIDGE_ISOLATION = env.str('BRIDGE_ISOLATION', default='warn').strip().lower()
