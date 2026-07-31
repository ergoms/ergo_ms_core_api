"""Удобный вызов аудита из ядра.

Ядро пишет в журнал через тот же мост, что и модули, — единая точка входа,
безопасная к сбоям и к отсутствию провайдера.
"""

import logging

logger = logging.getLogger('core.audit')


def audit_log(action, *, source_module='core.cms.adp', request=None, actor=None,
              entity=None, changes=None, meta=None, severity='info'):
    """Записать действие в единый журнал. Никогда не бросает исключение наружу."""
    try:
        from src.core.integrations import bridge
        from src.core.integrations.module_contracts import AUDIT_RECORD
        bridge.call(
            AUDIT_RECORD,
            action=action,
            source_module=source_module,
            request=request,
            actor=actor,
            entity=entity,
            changes=changes,
            meta=meta,
            severity=severity,
        )
    except Exception:
        logger.debug('audit_log fail: %s', action, exc_info=True)
