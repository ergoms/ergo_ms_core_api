"""
Однострочный access-лог в стиле Django runserver — и для daphne, и для runserver.

Формат: "GET /api/foo/ HTTP/1.1" 200
Логгер: django.server (как у runserver), уровень INFO.
"""

from __future__ import annotations

import logging

logger = logging.getLogger('django.server')


class AccessLogMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        response = self.get_response(request)
        try:
            method = request.method or '-'
            # path без query — без риска утечки токенов из query string
            path = request.path or '/'
            proto = request.META.get('SERVER_PROTOCOL', 'HTTP/1.1')
            status = getattr(response, 'status_code', '-')
            logger.info('"%s %s %s" %s', method, path, proto, status)
        except Exception:
            # access-лог не должен ломать ответ
            pass
        return response
