"""Непрозрачная ссылка и подпись контекста сессии на уведомлении."""

from src.core.integrations import bridge
from src.core.integrations.module_contracts import NOTIFICATIONS_SCOPE_LABELS

SCOPE_REF_MAX_LENGTH = 64
SCOPE_LABEL_MAX_LENGTH = 255


def normalize_scope_ref(value) -> str:
    if value is None:
        return ''
    text = str(value).strip()
    if not text:
        return ''
    return text[:SCOPE_REF_MAX_LENGTH]


def normalize_scope_label(value) -> str:
    if value is None:
        return ''
    text = ' '.join(str(value).split())
    if not text:
        return ''
    return text[:SCOPE_LABEL_MAX_LENGTH]


def resolve_scope_labels(scope_refs) -> dict[str, str]:
    refs = []
    seen = set()
    for raw in scope_refs or ():
        ref = normalize_scope_ref(raw)
        if ref and ref not in seen:
            seen.add(ref)
            refs.append(ref)
    if not refs:
        return {}
    try:
        raw = bridge.call(NOTIFICATIONS_SCOPE_LABELS, scope_refs=refs, default={})
    except Exception:
        return {}
    if not isinstance(raw, dict):
        return {}
    return {
        normalize_scope_ref(key): normalize_scope_label(value)
        for key, value in raw.items()
        if normalize_scope_ref(key) and normalize_scope_label(value)
    }
