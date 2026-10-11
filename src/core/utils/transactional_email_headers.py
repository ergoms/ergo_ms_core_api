"""Общие transactional-заголовки исходящих писем (Message-ID, List-Unsubscribe)."""

from __future__ import annotations

from email.utils import formataddr, formatdate, make_msgid, parseaddr
from urllib.parse import urlparse

from django.conf import settings


def relabel_from_display_name(from_email: str | None, display_name: str | None) -> str:
    """Подставить отображаемое имя, сам адрес SMTP не менять."""
    label = (display_name or '').strip()
    _old, addr = parseaddr(from_email or '')
    if not label or not addr:
        return from_email or ''
    return formataddr((label, addr))


def message_id_domain(from_email: str | None = None) -> str:
    """Домен для Message-ID: совпадает с From / FRONTEND_BASE_URL, не hostname VPS."""
    _name, addr = parseaddr(from_email or '')
    if '@' in addr:
        return addr.rsplit('@', 1)[-1].lower()
    base = getattr(settings, 'FRONTEND_BASE_URL', '') or ''
    host = urlparse(base).hostname
    if host:
        return host.lower()
    return 'localhost'


def apply_transactional_email_headers(
    message,
    *,
    from_email: str,
    unsubscribe_url: str | None = None,
) -> None:
    """Date, Message-ID, Reply-To, Auto-Submitted; опционально List-Unsubscribe."""
    _name, addr_email = parseaddr(from_email or '')
    if addr_email:
        message.reply_to = [addr_email]
    message.extra_headers['Message-ID'] = make_msgid(domain=message_id_domain(from_email))
    message.extra_headers['Date'] = formatdate(localtime=True)
    message.extra_headers['Auto-Submitted'] = 'auto-generated'
    url = (unsubscribe_url or '').strip()
    if url:
        message.extra_headers['List-Unsubscribe'] = f'<{url}>'
        message.extra_headers['List-Unsubscribe-Post'] = 'List-Unsubscribe=One-Click'
