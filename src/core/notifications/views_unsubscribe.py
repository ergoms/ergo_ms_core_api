"""Публичная страница отписки от писем уведомлений: GET подтверждает, POST пишет."""

from __future__ import annotations

from django.http import HttpResponse
from django.shortcuts import render
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods

from .email_unsubscribe import disable_email_channel, unsign_unsubscribe_token

_TEMPLATE = 'notifications/email_unsubscribe.html'


def _html_page(request, *, mode: str, token: str = '') -> HttpResponse:
    return render(
        request,
        _TEMPLATE,
        {'mode': mode, 'token': token},
        content_type='text/html; charset=utf-8',
    )


def _request_token(request) -> str:
    token = request.GET.get('token') or request.POST.get('token') or ''
    return str(token).strip()


@csrf_exempt
@require_http_methods(['GET', 'POST'])
def notification_email_unsubscribe(request):
    token = _request_token(request)
    payload = unsign_unsubscribe_token(token)
    if request.method == 'GET':
        return _html_page(request, mode='confirm', token=token)
    if payload:
        disable_email_channel(user_public_id=payload['user_public_id'])
    return _html_page(request, mode='done')
