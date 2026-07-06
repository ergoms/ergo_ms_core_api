from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any

ENVELOPE_VERSION = 1

WS_CONTROL_TOPIC = 'ws:control'
WS_AUTH_EVENT = 'ws_auth'
WS_AUTH_OK_EVENT = 'ws_auth_ok'
PRESENCE_PING_EVENT = 'presence_ping'
PRESENCE_USER_TOPIC = 'presence:user'


def is_envelope(content: Any) -> bool:
    return (
        isinstance(content, dict)
        and content.get('v') == ENVELOPE_VERSION
        and isinstance(content.get('type'), str)
        and 'payload' in content
    )


def parse_envelope(content: Any) -> dict[str, Any] | None:
    if not is_envelope(content):
        return None
    return content


def build_envelope(*, topic: str, event_type: str, payload: Any) -> dict[str, Any]:
    return {
        'v': ENVELOPE_VERSION,
        'id': str(uuid.uuid4()),
        'topic': topic,
        'type': event_type,
        'payload': payload,
        'ts': datetime.now(timezone.utc).isoformat(),
    }
