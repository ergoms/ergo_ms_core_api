"""
ModuleBridge — фасад единого механизма межмодульного взаимодействия.

Публичный API (стабильный):

    bridge.provide(name, handler, *, override=False)
    bridge.provide_many(group, key, obj)
    bridge.subscribe(event, handler)

    bridge.has(name) -> bool
    bridge.call(name, *args, default=None, **kwargs) -> Any
    bridge.emit(event, **payload) -> list[Any]
    bridge.all(group) -> dict[str, Any]

    bridge.unregister(name)
    bridge.unsubscribe(event, handler)
    bridge.reset()                                  # для тестов

Декораторы:

    @bridge.provide_op('module.operation')
    def op(...): ...

    @bridge.subscribe_to('module.event')
    def handler(**payload): ...

Все методы делегируются Transport (для операций) и EventBus (для событий).
Используются LocalTransport / LocalEventBus (монолитный режим).
``BRIDGE_TRANSPORT`` / ``BRIDGE_EVENT_BUS`` допускают только ``local``.
"""

from __future__ import annotations

import logging
from typing import Any, Callable

from .transports import EventBus, LocalEventBus, LocalTransport, Transport

logger = logging.getLogger('integrations.bridge')


class ModuleBridge:
    """Фасад над Transport + EventBus. Используется как класс-синглтон."""

    _transport: Transport = LocalTransport()
    _event_bus: EventBus = LocalEventBus()

    @classmethod
    def configure(cls, *, transport: Transport | None = None,
                  event_bus: EventBus | None = None) -> None:
        """
        Подменить транспорт/шину (например, при старте Django через settings
        или в тестах). Все ранее зарегистрированные провайдеры теряются.
        """
        if transport is not None:
            cls._transport = transport
            logger.info("ModuleBridge transport set to %s", type(transport).__name__)
        if event_bus is not None:
            cls._event_bus = event_bus
            logger.info("ModuleBridge event bus set to %s", type(event_bus).__name__)

    # --- single-provider operations ---------------------------------------

    @classmethod
    def provide(
        cls,
        name: str,
        handler: Callable[..., Any],
        *,
        override: bool = False,
    ) -> None:
        cls._transport.provide(name, handler, override=override)

    @classmethod
    def provide_op(cls, name: str, *, override: bool = False) -> Callable:
        """Декораторная форма provide(). Применять к функции-обработчику."""

        def decorator(func: Callable[..., Any]) -> Callable[..., Any]:
            cls._transport.provide(name, func, override=override)
            return func

        return decorator

    @classmethod
    def has(cls, name: str) -> bool:
        return cls._transport.has(name)

    @classmethod
    def call(
        cls,
        name: str,
        *args: Any,
        default: Any = None,
        **kwargs: Any,
    ) -> Any:
        """
        Вызвать зарегистрированную операцию по строковому имени.

        Если провайдер отсутствует — вернуть default (по умолчанию None).
        Никаких эвристик и исключений. Потребитель сам при необходимости
        проверяет bridge.has(name) или передаёт default=[]/default=False.
        """
        return cls._transport.call(name, args, kwargs, default)

    @classmethod
    def unregister(cls, name: str) -> None:
        cls._transport.unregister(name)

    # --- multi-provider groups -------------------------------------------

    @classmethod
    def provide_many(cls, group: str, key: str, obj: Any) -> None:
        cls._transport.provide_many(group, key, obj)

    @classmethod
    def all(cls, group: str) -> dict[str, Any]:
        return cls._transport.all(group)

    @classmethod
    def unregister_many(cls, group: str, key: str) -> None:
        cls._transport.unregister_many(group, key)

    # --- events ----------------------------------------------------------

    @classmethod
    def subscribe(cls, event: str, handler: Callable[..., Any]) -> None:
        cls._event_bus.subscribe(event, handler)

    @classmethod
    def subscribe_to(cls, event: str) -> Callable:
        """Декораторная форма subscribe(). Применять к функции-обработчику."""

        def decorator(func: Callable[..., Any]) -> Callable[..., Any]:
            cls._event_bus.subscribe(event, func)
            return func

        return decorator

    @classmethod
    def unsubscribe(cls, event: str, handler: Callable[..., Any]) -> None:
        cls._event_bus.unsubscribe(event, handler)

    @classmethod
    def emit(cls, event: str, **payload: Any) -> list[Any]:
        """
        Вещать событие с именем event. Возвращает список результатов
        всех подписчиков. Если подписчиков нет — пустой список.
        """
        return cls._event_bus.emit(event, payload)

    @classmethod
    def emit_first(cls, event: str, **payload: Any) -> Any:
        """
        Вещать событие и вернуть первый не-None результат подписчиков
        (удобно для permission-check и подобных голосований).
        """
        for result in cls._event_bus.emit(event, payload):
            if result is not None:
                return result
        return None

    # --- testing ---------------------------------------------------------

    @classmethod
    def reset(cls) -> None:
        cls._transport.reset()
        cls._event_bus.reset()


bridge = ModuleBridge
