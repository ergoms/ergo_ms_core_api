"""Platform-ops пакетов справки: публикация ядра и подпись чтения."""

from __future__ import annotations

import logging

from django.core.exceptions import ValidationError

from src.core.integrations import bridge
from src.core.integrations.module_contracts import (
    CORE_KNOWLEDGE_PACK,
    CORE_KNOWLEDGE_SIGN_READ,
)
from src.core.utils.knowledge_pack import (
    current_core_pack,
    restore_pack_descriptors_from_media,
    sign_knowledge_read,
)

logger = logging.getLogger('integrations.knowledge')


@bridge.provide_op(CORE_KNOWLEDGE_PACK)
def _core_knowledge_pack(**_):
    return current_core_pack()


@bridge.provide_op(CORE_KNOWLEDGE_SIGN_READ)
def _core_knowledge_sign_read(*, path: str = '', **_):
    try:
        return sign_knowledge_read(path, owner=None)
    except (ValidationError, ValueError) as exc:
        logger.info('Отказ подписи пакета справки: %s', exc)
        return None


def load_knowledge_providers() -> None:
    """Восстановить дескрипторы с диска после регистрации ops."""
    from src.core.utils.knowledge_pack import _is_core_process

    if not _is_core_process():
        # Иначе CLI на хосте модулей читает пустой current.json у себя и не идёт на ядро.
        bridge.unregister(CORE_KNOWLEDGE_PACK)
        bridge.unregister(CORE_KNOWLEDGE_SIGN_READ)
    try:
        restore_pack_descriptors_from_media()
    except Exception:
        logger.debug('Не удалось восстановить пакеты справки с media', exc_info=True)
