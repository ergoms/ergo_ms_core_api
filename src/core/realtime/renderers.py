import json

from rest_framework.renderers import BaseRenderer


class EventStreamRenderer(BaseRenderer):
    """Рендерер для SSE: согласование Accept: text/event-stream в DRF."""

    media_type = 'text/event-stream'
    format = 'event-stream'
    charset = 'utf-8'
    render_style = 'binary'

    def render(self, data, accepted_media_type=None, renderer_context=None):
        if data is None:
            return b''
        if isinstance(data, (bytes, memoryview)):
            return bytes(data)
        return json.dumps(data, ensure_ascii=False).encode(self.charset)
