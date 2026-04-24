"""
Celery-шина событий для микросервисного режима (стаб; будет реализован отдельной фазой).

Идея реализации:

1. Подписка (`subscribe`).
   Каждый подписчик регистрируется как Celery-таска при старте сервиса
   (например, через @shared_task с именем 'bridge.event.<event_name>').
   В реестре EventBus хранятся имена тасок, а не сами callables.

2. Вещание (`emit`).
   - Для асинхронных событий (fire-and-forget): celery_app.send_task(...)
     для каждой подписки; вернуть пустой список.
   - Для синхронных (например, 'adp.permission_check' с агрегацией результатов):
     celery.group([signature(...) for sig in subs]).apply_async().get(timeout=...)
     чтобы получить список ответов.

3. Discovery подписчиков — общий backend (Redis/DB), куда сервисы пишут
   список своих хэндлеров при старте; emit читает оттуда подписчиков.

4. Сериализация — JSON (Celery-стандарт). Payload событий должен быть
   JSON-friendly: только примитивы, dict, list, dataclasses.

5. Конфигурация:

       BRIDGE_EVENT_BUS = 'celery'
       BRIDGE_CELERY_TIMEOUT = 5  # секунды на синхронный сбор результатов

6. Деградация: если Celery недоступен, emit логирует ошибку и возвращает [].

Пока реализация не нужна (монолит); стаб-класс выбрасывает NotImplementedError
при любой попытке использовать.
"""

from __future__ import annotations

from typing import Any, Callable


class CeleryEventBus:
    """Стаб Celery-шины событий. Реализация — в следующей фазе."""

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        raise NotImplementedError(
            "CeleryEventBus is not implemented yet. "
            "Use BRIDGE_EVENT_BUS='local' for monolithic mode."
        )

    def subscribe(self, event: str, handler: Callable[..., Any]) -> None:
        raise NotImplementedError

    def unsubscribe(self, event: str, handler: Callable[..., Any]) -> None:
        raise NotImplementedError

    def emit(self, event: str, payload: dict[str, Any]) -> list[Any]:
        raise NotImplementedError

    def reset(self) -> None:
        raise NotImplementedError
