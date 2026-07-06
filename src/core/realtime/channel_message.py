from __future__ import annotations

from typing import Any

from src.core.realtime.envelope import build_envelope

CHANNEL_EVENT_TYPE = 'realtime_event'


def build_channel_message(*, topic: str, event_type: str, payload: Any) -> dict[str, Any]:
    return {
        'type': CHANNEL_EVENT_TYPE,
        'envelope': build_envelope(topic=topic, event_type=event_type, payload=payload),
    }
