"""
HTTP-транспорт для микросервисного режима (стаб; будет реализован отдельной фазой).

Идея реализации:

1. Регистрация (`provide`).
   Каждое API-приложение, экспонирующее операции, поднимает общий
   blueprint-роутер `/bridge/call/<name>`. На стороне provider операции
   остаются in-process (под капотом — LocalTransport), а HTTP-роутер
   просто их проксирует.

2. Удалённый вызов (`call`).
   Ищем в settings.BRIDGE_REMOTES URL для имени операции по префиксу
   (например, 'my_module.*' -> 'http://my-module-svc:8000').
   Делаем requests.post(url + '/bridge/call/' + name,
                        json={'args': [...], 'kwargs': {...}}).
   Сериализация: JSON (значит, операции, уходящие в HTTP, должны
   принимать только примитивы — int/str/dict/list/bool — и dataclasses).

3. Service discovery — статический BRIDGE_REMOTES либо динамический
   (Consul/etcd/K8s DNS) поверх Provider-интерфейса.

4. Сервисная аутентификация — заголовок X-Bridge-Service + общий секрет
   или подписанный JWT.

5. Multi-provider (`provide_many` / `all`) — провайдеры регистрируются
   через registry-сервис; `all(group)` запрашивает у registry список
   эндпоинтов и возвращает объекты-прокси, методы которых превращаются
   в HTTP-вызовы.

6. Fallback при недоступности удалённого сервиса — возвращать default,
   как при отсутствии провайдера в LocalTransport, и логировать ошибку.

Для активации в settings нужно будет указать:

    BRIDGE_TRANSPORT = 'http'        # или 'routing'
    BRIDGE_REMOTES = {
        'my_module.*': 'http://my-module-svc:8000',
        ...
    }

Пока реализация не нужна (монолит); стаб-класс выбрасывает NotImplementedError
при любой попытке использовать.
"""

from __future__ import annotations

from typing import Any, Callable


class HttpTransport:
    """Стаб HTTP-транспорта. Реализация — в следующей фазе."""

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        raise NotImplementedError(
            "HttpTransport is not implemented yet. "
            "Use BRIDGE_TRANSPORT='local' for monolithic mode."
        )

    def provide(
        self,
        name: str,
        handler: Callable[..., Any],
        *,
        override: bool = False,
    ) -> None:
        raise NotImplementedError

    def provide_many(self, group: str, key: str, obj: Any) -> None:
        raise NotImplementedError

    def has(self, name: str) -> bool:
        raise NotImplementedError

    def call(
        self,
        name: str,
        args: tuple[Any, ...],
        kwargs: dict[str, Any],
        default: Any,
    ) -> Any:
        raise NotImplementedError

    def all(self, group: str) -> dict[str, Any]:
        raise NotImplementedError

    def unregister(self, name: str) -> None:
        raise NotImplementedError

    def unregister_many(self, group: str, key: str) -> None:
        raise NotImplementedError

    def reset(self) -> None:
        raise NotImplementedError
