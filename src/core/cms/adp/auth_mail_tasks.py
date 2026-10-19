"""Письма входа и приглашений через Celery, с синхронным запасным путём."""

from __future__ import annotations

import logging
from collections.abc import Callable

from celery import shared_task
from django.db import transaction

logger = logging.getLogger('celery.core.cms.adp')


@shared_task(name='core.cms.adp.send_password_reset_code_email')
def send_password_reset_code_email_task(email: str, code: str) -> None:
    from src.core.cms.adp.services.password_reset_mail import send_password_reset_code_email

    ok, error = send_password_reset_code_email(email, code)
    if not ok:
        logger.warning('Письмо с кодом сброса не ушло на %s: %s', email, error)


@shared_task(name='core.cms.adp.send_admin_password_reset_email')
def send_admin_password_reset_email_task(email: str) -> None:
    from src.core.cms.adp.services.password_reset_mail import send_admin_password_reset_email

    ok, error = send_admin_password_reset_email(email)
    if not ok:
        logger.warning('Письмо о сбросе пароля администратором не ушло на %s: %s', email, error)


@shared_task(name='core.cms.adp.send_registration_invitation_email')
def send_registration_invitation_email_task(email: str, invite_url: str, ttl_days: int) -> None:
    from src.core.cms.adp.services.registration_invitation_mail import (
        send_registration_invitation_email,
    )

    ok, error = send_registration_invitation_email(email, invite_url, ttl_days)
    if not ok:
        logger.warning('Письмо-приглашение не ушло на %s: %s', email, error)


def dispatch_auth_email(task, args: tuple, sync_send: Callable[[], tuple]) -> tuple:
    """Ставит письмо в очередь после commit. Без брокера отправляет сразу."""

    def _enqueue() -> None:
        try:
            task.delay(*args)
        except Exception:
            logger.exception('Брокер недоступен, письмо уходит синхронно')
            sync_send()

    if transaction.get_connection().in_atomic_block:
        transaction.on_commit(_enqueue)
        return True, None
    try:
        task.delay(*args)
    except Exception:
        logger.exception('Брокер недоступен, письмо уходит синхронно')
        return sync_send()
    return True, None
