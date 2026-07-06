from __future__ import annotations


class RealtimeEnvelopeConsumerMixin:
    """Проброс envelope клиенту WebSocket без преобразования формата."""

    async def realtime_event(self, event: dict) -> None:
        envelope = event.get('envelope')
        if envelope:
            await self.send_json(envelope)
