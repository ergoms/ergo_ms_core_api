"""
Настройки ModuleBridge — единого механизма межмодульного взаимодействия.

Определяет, какие реализации Transport и EventBus использовать на запуске.
В монолитном режиме (по умолчанию) используются in-process реализации
``LocalTransport`` / ``LocalEventBus`` — никаких внешних зависимостей.

В микросервисном режиме можно переключить через переменные окружения:

    BRIDGE_TRANSPORT=http        # 'local' | 'http'
    BRIDGE_EVENT_BUS=celery      # 'local' | 'celery'

Конкретные транспорты подключаются в ``src.core.integrations.apps.ready()``.
HTTP / Celery — стабы (см. ``src/core/integrations/transports/``); включение
сейчас приведёт к ``NotImplementedError`` на старте.
"""

from src.config.env import env

BRIDGE_TRANSPORT = env.str('BRIDGE_TRANSPORT', default='local').strip().lower()
BRIDGE_EVENT_BUS = env.str('BRIDGE_EVENT_BUS', default='local').strip().lower()

BRIDGE_REMOTES: dict[str, str] = {}
