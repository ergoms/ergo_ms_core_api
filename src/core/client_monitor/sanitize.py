"""Санитизация payload мониторинга клиента перед записью в БД."""

from __future__ import annotations

from datetime import datetime
from typing import Any
from urllib.parse import urlsplit

from django.utils import timezone
from django.utils.dateparse import parse_datetime

from src.core.audit.redaction import redact

ALLOWED_KINDS = frozenset({'nav', 'api', 'error', 'warn', 'lifecycle'})

_MAX_PAYLOAD_KEYS = 24
_MAX_STR = 500
_MAX_STACK = 2000
_MAX_PATH = 300
_MAX_UA = 512
_MAX_VIEWPORT = 32
_MAX_LABEL = 255
_MAX_VERSION = 64
_MAX_CLAIM_KEYS = 20


def _truncate(value: str, limit: int) -> str:
    if len(value) <= limit:
        return value
    return f'{value[:limit]}…'


def sanitize_path(raw: Any) -> str:
    if not isinstance(raw, str) or not raw.strip():
        return ''
    text = raw.strip()
    try:
        parts = urlsplit(text if '://' in text else f'http://local{text if text.startswith("/") else "/" + text}')
        path = parts.path or '/'
    except Exception:
        path = text.split('?', 1)[0]
    return _truncate(path, _MAX_PATH)


def sanitize_string(raw: Any, limit: int = _MAX_STR) -> str:
    if raw is None:
        return ''
    if not isinstance(raw, (str, int, float, bool)):
        return _truncate(str(type(raw).__name__), limit)
    return _truncate(str(raw), limit)


def sanitize_claim_keys(raw: Any) -> list[str]:
    if not isinstance(raw, (list, tuple)):
        return []
    keys: list[str] = []
    for item in raw:
        if not isinstance(item, str):
            continue
        key = item.strip()[:64]
        if key and key not in keys:
            keys.append(key)
        if len(keys) >= _MAX_CLAIM_KEYS:
            break
    return keys


def sanitize_session_meta(raw: Any) -> dict[str, Any]:
    if not isinstance(raw, dict):
        return {}
    return {
        'user_agent': sanitize_string(raw.get('user_agent'), _MAX_UA),
        'language': sanitize_string(raw.get('language'), 32),
        'timezone': sanitize_string(raw.get('timezone'), 64),
        'viewport': sanitize_string(raw.get('viewport'), _MAX_VIEWPORT),
        'client_version': sanitize_string(raw.get('client_version'), _MAX_VERSION),
        'scope_claim_keys': sanitize_claim_keys(raw.get('scope_claim_keys')),
    }


def _parse_client_ts(raw: Any) -> datetime:
    if isinstance(raw, (int, float)):
        # ms or seconds
        ts = float(raw)
        if ts > 1e12:
            ts = ts / 1000.0
        try:
            return datetime.fromtimestamp(ts, tz=timezone.get_current_timezone())
        except (OverflowError, OSError, ValueError):
            return timezone.now()

    if isinstance(raw, str) and raw.strip():
        parsed = parse_datetime(raw.strip())
        if parsed is not None:
            if timezone.is_naive(parsed):
                return timezone.make_aware(parsed, timezone.get_current_timezone())
            return parsed
    return timezone.now()


def sanitize_payload(kind: str, raw: Any) -> dict[str, Any]:
    if not isinstance(raw, dict):
        return {}
    redacted = redact(raw)
    if not isinstance(redacted, dict):
        return {}

    cleaned: dict[str, Any] = {}
    for index, (key, value) in enumerate(redacted.items()):
        if index >= _MAX_PAYLOAD_KEYS:
            cleaned['dropped_keys'] = True
            break
        if not isinstance(key, str):
            continue
        key_l = key.lower()
        if key_l in {'path', 'from', 'to', 'route', 'route_name', 'endpoint', 'url'}:
            cleaned[key] = sanitize_path(value)
        elif key_l in {'stack', 'component_stack'}:
            cleaned[key] = sanitize_string(value, _MAX_STACK)
        elif key_l in {'message', 'detail', 'status_text', 'method', 'request_id', 'component'}:
            cleaned[key] = sanitize_string(value, _MAX_STR)
        elif key_l in {'status', 'duration_ms', 'seq'}:
            if isinstance(value, bool):
                continue
            if isinstance(value, (int, float)):
                cleaned[key] = int(value) if key_l != 'duration_ms' else max(0, int(value))
            elif isinstance(value, str) and value.isdigit():
                cleaned[key] = int(value)
        elif isinstance(value, (str, int, float, bool)) or value is None:
            if isinstance(value, str):
                cleaned[key] = sanitize_string(value, _MAX_STR)
            else:
                cleaned[key] = value
        else:
            cleaned[key] = sanitize_string(str(type(value).__name__), 64)
    cleaned.setdefault('kind', kind)
    return cleaned


def sanitize_event(raw: Any) -> dict[str, Any] | None:
    if not isinstance(raw, dict):
        return None
    kind = str(raw.get('kind', '')).lower().strip()
    if kind not in ALLOWED_KINDS:
        return None
    seq_raw = raw.get('seq')
    try:
        seq = int(seq_raw)
    except (TypeError, ValueError):
        return None
    if seq < 1:
        return None
    return {
        'seq': seq,
        'kind': kind,
        'created_at': _parse_client_ts(raw.get('ts') or raw.get('created_at')),
        'payload': sanitize_payload(kind, raw.get('payload') or raw.get('data') or {}),
    }


def user_label(user) -> str:
    if user is None:
        return ''
    get_full_name = getattr(user, 'get_full_name', None)
    if callable(get_full_name):
        full = (get_full_name() or '').strip()
        if full:
            return _truncate(full, _MAX_LABEL)
    username = getattr(user, 'username', None) or getattr(user, 'email', None) or ''
    return _truncate(str(username), _MAX_LABEL)
