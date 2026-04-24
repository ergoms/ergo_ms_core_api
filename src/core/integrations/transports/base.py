"""
Интерфейсы транспортного слоя ModuleBridge.

Transport отвечает за регистрацию и вызов операций (single- и multi-provider).
EventBus — за подписку и вещание событий с N подписчиками.

Обе абстракции существуют, чтобы публичное API bridge оставалось неизменным
при переключении между in-process (монолит), HTTP (микросервисы)
и брокерными (Celery/Redis) реализациями.
"""

from __future__ import annotations

from typing import Any, Callable, Protocol, runtime_checkable


@runtime_checkable
class Transport(Protocol):
    """Контракт транспорта операций bridge.call / bridge.provide / bridge.all."""

    def provide(
        self,
        name: str,
        handler: Callable[..., Any],
        *,
        override: bool = False,
    ) -> None:
        """Зарегистрировать единственного провайдера операции по строковому имени."""

    def provide_many(self, group: str, key: str, obj: Any) -> None:
        """Зарегистрировать одного из нескольких провайдеров группы."""

    def has(self, name: str) -> bool:
        """Истина, если для имени зарегистрирован провайдер."""

    def call(
        self,
        name: str,
        args: tuple[Any, ...],
        kwargs: dict[str, Any],
        default: Any,
    ) -> Any:
        """Вызвать провайдера; вернуть default, если провайдер отсутствует."""

    def all(self, group: str) -> dict[str, Any]:
        """Вернуть словарь всех провайдеров группы (копия)."""

    def unregister(self, name: str) -> None:
        """Снять регистрацию операции (для тестов и hot-reload)."""

    def unregister_many(self, group: str, key: str) -> None:
        """Снять одну регистрацию из multi-provider группы."""

    def reset(self) -> None:
        """Полная очистка реестра — для тестов."""


@runtime_checkable
class EventBus(Protocol):
    """Контракт шины событий bridge.subscribe / bridge.emit."""

    def subscribe(self, event: str, handler: Callable[..., Any]) -> None:
        """Подписать обработчик на событие."""

    def unsubscribe(self, event: str, handler: Callable[..., Any]) -> None:
        """Снять подписку обработчика."""

    def emit(self, event: str, payload: dict[str, Any]) -> list[Any]:
        """
        Вещать событие; вернуть список результатов всех подписчиков.

        Исключения внутри обработчиков логируются и заменяются на None.
        Если подписчиков нет — возвращается пустой список.
        """

    def reset(self) -> None:
        """Полная очистка подписок — для тестов."""
