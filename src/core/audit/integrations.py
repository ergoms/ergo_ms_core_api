"""Регистрация публичного API аудита в ModuleBridge.

Модули пишут в журнал только через `bridge.call('audit.record', ...)` и
описывают свои действия через `bridge.provide_many('audit.action_definitions', ...)`,
без прямого импорта моделей/сервиса этого приложения.
"""

from src.core.integrations import bridge

from .core_actions import CORE_AUDIT_SECTION, CORE_SETTINGS_SECTION
from .service import AuditService


@bridge.provide_op('audit.record')
def _record(
    *,
    action,
    source_module='',
    actor=None,
    request=None,
    entity=None,
    changes=None,
    meta=None,
    severity='info',
    organization_id=None,
    department_id=None,
):
    """Зафиксировать действие пользователя в едином журнале.

    Инициатор, IP, User-Agent, организация и request_id подхватываются из
    контекста запроса автоматически — обычно достаточно передать `action`
    и (по желанию) `entity` / `changes`.
    """
    kwargs = dict(
        action=action,
        source_module=source_module,
        request=request,
        entity=entity,
        changes=changes,
        meta=meta,
        severity=severity,
    )
    # actor/organization/department переопределяют контекст только если заданы.
    if actor is not None:
        kwargs['actor'] = actor
    if organization_id is not None:
        kwargs['organization_id'] = organization_id
    if department_id is not None:
        kwargs['department_id'] = department_id

    AuditService.record(**kwargs)


# Каталог действий самого ядра.
bridge.provide_many('audit.action_definitions', key=CORE_AUDIT_SECTION['module'], obj=CORE_AUDIT_SECTION)
bridge.provide_many('audit.action_definitions', key=CORE_SETTINGS_SECTION['module'], obj=CORE_SETTINGS_SECTION)
