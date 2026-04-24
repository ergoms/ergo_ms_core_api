"""
Module Bridge — единый механизм межмодульного взаимодействия.

Модули регистрируют операции и подписки по строковым именам
('module.operation', 'module.event'), потребители обращаются
через bridge.call / bridge.emit без прямых импортов другого модуля.

Пример провайдера (modules/organizations/api/integrations.py):

    from src.core.integrations import bridge
    from .models import OrganizationMember

    @bridge.provide_op('organizations.get_user_department_ids')
    def _get_user_department_ids(user):
        if not user or not getattr(user, 'is_authenticated', False):
            return []
        return list(
            OrganizationMember.objects
            .filter(user=user, department__isnull=False)
            .values_list('department_id', flat=True)
        )

    @bridge.subscribe_to('adp.permission_check')
    def _on_permission_check(*, user, module_name, permission_key, **_):
        ...

Пример потребителя (любой другой модуль):

    from src.core.integrations import bridge

    dept_ids = bridge.call(
        'organizations.get_user_department_ids',
        user=request.user,
        default=[],
    )

    if not bridge.has('organizations.get_organization'):
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
