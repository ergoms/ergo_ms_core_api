"""Публичная отписка от email-канала уведомлений: токен, URL, выключение предпочтения."""

from __future__ import annotations

import logging
from urllib.parse import urlencode

from django.contrib.auth import get_user_model
from django.core.signing import BadSignature, TimestampSigner

from . import catalog
from .models import NotificationPreference
from .preferences import GLOBAL_KEY

logger = logging.getLogger('core.notifications')

UNSUBSCRIBE_PATH = '/api/notifications/email/unsubscribe/'
_SIGNER_SALT = 'core.notifications.email.unsubscribe'
_CHANNEL_EMAIL = catalog.CHANNEL_EMAIL


def _signer() -> TimestampSigner:
    return TimestampSigner(salt=_SIGNER_SALT)


def sign_unsubscribe_token(*, user_public_id: str, channel: str = _CHANNEL_EMAIL) -> str:
    payload = f'{channel}:{user_public_id}'
    return _signer().sign(payload)


def unsign_unsubscribe_token(token: str) -> dict | None:
    raw = str(token or '').strip()
    if not raw:
        return None
    try:
        payload = _signer().unsign(raw)
    except BadSignature:
        return None
    channel, separator, user_public_id = payload.partition(':')
    if not separator or channel != _CHANNEL_EMAIL:
        return None
    public_id = str(user_public_id or '').strip()
    if not public_id:
        return None
    return {'channel': channel, 'user_public_id': public_id}


def is_absolute_public_url(value: str) -> bool:
    return str(value or '').startswith(('http://', 'https://'))


def notification_public_origin() -> str:
    from src.config.nginx_runtime import inferred_public_origins, nginx_public_origin

    origins = inferred_public_origins()
    if origins:
        return origins[0].rstrip('/')
    origin = (nginx_public_origin() or '').strip().rstrip('/')
    if origin:
        return origin
    from django.conf import settings

    return str(getattr(settings, 'FRONTEND_BASE_URL', '') or '').rstrip('/')


def build_unsubscribe_url(*, user_public_id: str) -> str:
    origin = notification_public_origin()
    if not is_absolute_public_url(origin):
        logger.warning('Notification public origin is empty; unsubscribe URL omitted.')
        return ''
    public_id = str(user_public_id or '').strip()
    if not public_id:
        return ''
    query = urlencode({'token': sign_unsubscribe_token(user_public_id=public_id)})
    return f'{origin.rstrip("/")}{UNSUBSCRIBE_PATH}?{query}'


def disable_email_channel(*, user_public_id: str) -> bool:
    """Выключить глобальный email-канал. Колокольчик и список отказов рассылки не трогает."""
    public_id = str(user_public_id or '').strip()
    if not public_id:
        return False
    user = get_user_model().objects.filter(public_id=public_id, is_active=True).first()
    if user is None:
        return False
    NotificationPreference.objects.update_or_create(
        user_id=user.pk,
        source_module=GLOBAL_KEY,
        event_key=GLOBAL_KEY,
        channel=_CHANNEL_EMAIL,
        defaults={'enabled': False},
    )
    return True
