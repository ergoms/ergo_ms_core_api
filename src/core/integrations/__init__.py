"""
Module Bridge — единый механизм межмодульного взаимодействия.

Модули регистрируют операции и подписки по строковым именам
('module.operation', 'module.event'), потребители обращаются
через bridge.call / bridge.emit без прямых импортов другого модуля.

Пример провайдера (modules/my_module/api/integrations.py):

    from src.core.integrations import bridge
    from .models import MyEntity

    @bridge.provide_op('my_module.get_user_entity_ids')
    def _get_user_entity_ids(user):
        if not user or not getattr(user, 'is_authenticated', False):
            return []
        return list(
            MyEntity.objects
            .filter(user=user)
            .values_list('id', flat=True)
        )

    @bridge.subscribe_to('adp.permission_check')
    def _on_permission_check(*, user, module_name, permission_key, **_):
        ...

Пример потребителя (любой другой модуль):

    from src.core.integrations import bridge

    entity_ids = bridge.call(
        'my_module.get_user_entity_ids',
        user=request.user,
        default=[],
    )

    if not bridge.has('my_module.get_entity'):
        return Response(...)

Если модуль-провайдер не подключён, bridge.call возвращает default
(тихо, без исключений), а bridge.emit — пустой список.

Подробнее о транспортах (in-process / HTTP / Celery) —
см. transports/base.py.
"""

from .bridge import ModuleBridge, bridge
from .exceptions import BridgeError, DuplicateProvider
from .isolation import BridgeIsolationError, BridgeIsolationWarning
from .transports import EventBus, LocalEventBus, LocalTransport, Transport

__all__ = [
    'ModuleBridge',
    'bridge',
    'BridgeError',
    'DuplicateProvider',
    'BridgeIsolationError',
    'BridgeIsolationWarning',
    'Transport',
    'EventBus',
    'LocalTransport',
    'LocalEventBus',
]
