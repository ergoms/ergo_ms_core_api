"""
Рендеринг формы письма для уведомления.

Каскад выбора (от частного к общему):
1. bridge.call('notifications.render_email.<module>', notification=...) — programmatic override,
   модуль возвращает dict {'subject', 'html_body', 'text_body', 'from_email'}.
2. Спека события из каталога (channels.email: subject / template_html / template_text).
3. Module provider 'notifications.email_templates'[key=module].get_spec(event_key)
   и его MODULE_DEFAULT.
4. Core fallback: notifications/email/default.html + title/body уведомления.

Контекст: базовый формирует ядро (build_base_email_context), модуль может
обогатить его через provide_many('notifications.email_context', key=<module>, obj=<callable>).
"""

import logging
from dataclasses import dataclass, field

from django.conf import settings
from django.template import Context, Template
from django.template.loader import render_to_string
from django.utils.html import strip_tags

from src.core.integrations import bridge
from src.core.integrations.exceptions import BridgeUnavailable
from src.core.integrations.module_contracts import (
    NOTIFICATIONS_EMAIL_CONTEXT_GROUP,
    NOTIFICATIONS_EMAIL_TEMPLATES_GROUP,
    NOTIFICATIONS_RENDER_EMAIL_PREFIX,
)

from . import catalog
from .email_unsubscribe import build_unsubscribe_url
from .frontend_route_url import (
    build_frontend_url_from_route,
    inbox_url,
    join_frontend_path,
)
from .scope import normalize_scope_label, normalize_scope_ref, resolve_scope_labels

logger = logging.getLogger('core.notifications')

EMAIL_CONTEXT_GROUP = NOTIFICATIONS_EMAIL_CONTEXT_GROUP
EMAIL_TEMPLATES_GROUP = NOTIFICATIONS_EMAIL_TEMPLATES_GROUP

CORE_DEFAULT_HTML = 'notifications/email/default.html'
CORE_DEFAULT_TXT = 'notifications/email/default.txt'


@dataclass(frozen=True)
class RelatedEmailImage:
    cid: str
    content: bytes
    subtype: str = 'png'
    filename: str = 'image.png'


@dataclass(frozen=True)
class EmailAttachment:
    filename: str
    content: bytes
    mimetype: str = 'application/octet-stream'


@dataclass
class RenderedEmail:
    subject: str
    html_body: str
    text_body: str
    from_email: str | None = None
    related_images: tuple[RelatedEmailImage, ...] = field(default_factory=tuple)
    attachments: tuple[EmailAttachment, ...] = field(default_factory=tuple)


def normalize_related_images(value) -> tuple[RelatedEmailImage, ...]:
    if not value:
        return ()
    result: list[RelatedEmailImage] = []
    seen: set[str] = set()
    for item in value:
        image = _as_related_image(item)
        if image is None or image.cid in seen or not image.content:
            continue
        seen.add(image.cid)
        result.append(image)
    return tuple(result)


def _as_related_image(item) -> RelatedEmailImage | None:
    if isinstance(item, RelatedEmailImage):
        cid = str(item.cid or '').strip()
        if not cid:
            return None
        subtype = str(item.subtype or 'png').split('/')[-1] or 'png'
        filename = str(item.filename or f'{cid}.{subtype}')
        return RelatedEmailImage(
            cid=cid,
            content=item.content,
            subtype=subtype,
            filename=filename,
        )
    if not isinstance(item, dict):
        return None
    cid = str(item.get('cid') or '').strip()
    content = item.get('content')
    if not cid or not isinstance(content, (bytes, bytearray)) or not content:
        return None
    subtype = str(item.get('subtype') or 'png').split('/')[-1] or 'png'
    filename = str(item.get('filename') or f'{cid}.{subtype}')
    return RelatedEmailImage(
        cid=cid,
        content=bytes(content),
        subtype=subtype,
        filename=filename,
    )


def _safe_attachment_name(name: str) -> str:
    clean = str(name or '').replace('\\', '/').rsplit('/', 1)[-1].replace('\x00', '').strip()
    return clean[:255] or 'attachment.bin'


def normalize_attachments(value) -> tuple[EmailAttachment, ...]:
    if not value:
        return ()
    result: list[EmailAttachment] = []
    seen: set[str] = set()
    for item in value:
        attachment = _as_attachment(item)
        if attachment is None or attachment.filename in seen:
            continue
        seen.add(attachment.filename)
        result.append(attachment)
    return tuple(result)


def _as_attachment(item) -> EmailAttachment | None:
    if isinstance(item, EmailAttachment):
        filename = _safe_attachment_name(item.filename)
        content = item.content
        mimetype = str(item.mimetype or 'application/octet-stream')
    elif isinstance(item, dict):
        filename = _safe_attachment_name(item.get('filename') or '')
        content = item.get('content')
        mimetype = str(item.get('mimetype') or 'application/octet-stream')
    else:
        return None
    if not isinstance(content, (bytes, bytearray)) or not content:
        return None
    if '/' not in mimetype:
        mimetype = 'application/octet-stream'
    return EmailAttachment(filename=filename, content=bytes(content), mimetype=mimetype)


def _with_attachments(rendered: RenderedEmail, attachments: tuple[EmailAttachment, ...]) -> RenderedEmail:
    if rendered.attachments:
        return rendered
    rendered.attachments = attachments
    return rendered


def _route_with_scope(notification) -> dict | None:
    route = getattr(notification, 'route', None)
    if not isinstance(route, dict):
        return None
    scope_ref = normalize_scope_ref(getattr(notification, 'scope_ref', None))
    if not scope_ref:
        return route
    query = dict(route.get('query') or {})
    if not query.get('scope_ref'):
        query['scope_ref'] = scope_ref
    return {**route, 'query': query}


def _resolve_action_url(notification) -> str:
    """Ссылка в письме: link_url → Vue-route → инбокс (без числового pk)."""
    base = getattr(settings, 'FRONTEND_BASE_URL', '') or ''
    link = (getattr(notification, 'link_url', None) or '').strip()
    if link:
        if link.lower().startswith(('http://', 'https://')):
            return link
        return join_frontend_path(base, link)
    routed = build_frontend_url_from_route(_route_with_scope(notification), base_url=base)
    if routed:
        return routed
    return inbox_url(base) if base else ''


def resolve_unsubscribe_url(notification=None) -> str:
    recipient = getattr(notification, 'recipient', None) if notification is not None else None
    public_id = getattr(recipient, 'public_id', None)
    if not public_id:
        return ''
    return build_unsubscribe_url(user_public_id=str(public_id))


def build_base_email_context(notification) -> dict:
    recipient = notification.recipient
    full_name = ''
    if recipient is not None:
        full_name = (
            f"{getattr(recipient, 'last_name', '')} {getattr(recipient, 'first_name', '')}"
        ).strip() or getattr(recipient, 'username', '')

    section = catalog.get_catalog().get(notification.source_module or '')
    module_label = section['module_label'] if section else (notification.source_module or '')
    event_spec = (section or {}).get('events', {}).get(notification.event_key or '') or {}
    stored_label = normalize_scope_label(getattr(notification, 'scope_label', ''))
    scope_ref = normalize_scope_ref(getattr(notification, 'scope_ref', None))
    scope_label = stored_label
    if not scope_label and scope_ref:
        scope_label = resolve_scope_labels([scope_ref]).get(scope_ref, '')

    return {
        'recipient': recipient,
        'recipient_name': full_name,
        'title': notification.title,
        'body': notification.body,
        'level': notification.level,
        'source_module': notification.source_module,
        'event_key': notification.event_key,
        'module_label': module_label,
        'event_label': event_spec.get('label') or '',
        'category_label': event_spec.get('category_label') or '',
        'scope_label': scope_label,
        'action_url': _resolve_action_url(notification),
        'unsubscribe_url': resolve_unsubscribe_url(notification),
        'meta': notification.meta or {},
    }


def _enrich_context(notification, base_context: dict) -> dict:
    provider = bridge.all(EMAIL_CONTEXT_GROUP).get(notification.source_module or '')
    if not callable(provider):
        return base_context
    try:
        enriched = provider(notification=notification, base_context=base_context)
        if isinstance(enriched, dict):
            return enriched
    except Exception:
        logger.exception(
            'email_context провайдер %s упал для notification=%s',
            notification.source_module, notification.pk,
        )
    return base_context


def _render_subject(template_string: str, context: dict, fallback: str) -> str:
    if not template_string:
        return fallback
    try:
        rendered = Template(template_string).render(Context(context)).strip()
        return rendered or fallback
    except Exception:
        logger.exception('Ошибка рендера subject-шаблона: %r', template_string)
        return fallback


def _render_template(template_name: str, context: dict) -> str | None:
    if not template_name:
        return None
    try:
        return render_to_string(template_name, context)
    except Exception:
        logger.exception('Шаблон письма %r не отрендерился', template_name)
        return None


def _try_programmatic(notification, context: dict) -> RenderedEmail | None:
    op = f'{NOTIFICATIONS_RENDER_EMAIL_PREFIX}{notification.source_module or ""}'
    if not notification.source_module:
        return None
    try:
        if not bridge.has(op):
            return None
    except BridgeUnavailable:
        logger.warning('Programmatic render %s: модуль не ответил', op)
        return None
    try:
        result = bridge.call(op, notification=notification, base_context=context)
    except Exception:
        logger.exception('Programmatic render %s упал', op)
        return None
    if not isinstance(result, dict) or not result.get('html_body'):
        return None
    return RenderedEmail(
        subject=result.get('subject') or notification.title,
        html_body=result['html_body'],
        text_body=result.get('text_body') or strip_tags(result['html_body']),
        from_email=result.get('from_email'),
        related_images=normalize_related_images(
            result.get('related_images') or context.get('related_images'),
        ),
        attachments=normalize_attachments(result.get('attachments') or context.get('attachments')),
    )


def _get_module_spec(notification) -> dict | None:
    """Спека из module provider (уровень D каскада)."""
    provider = bridge.all(EMAIL_TEMPLATES_GROUP).get(notification.source_module or '')
    if provider is None:
        return None
    spec = None
    get_spec = getattr(provider, 'get_spec', None)
    if callable(get_spec):
        try:
            spec = get_spec(notification.event_key)
        except Exception:
            logger.exception(
                'email_templates провайдер %s упал', notification.source_module,
            )
    if spec is None:
        module_default = getattr(provider, 'MODULE_DEFAULT', '')
        if module_default:
            spec = {'template_html': module_default}
    return spec if isinstance(spec, dict) else None


def _render_from_spec(spec: dict, notification, context: dict) -> RenderedEmail | None:
    html = _render_template(spec.get('template_html') or '', context)
    if html is None and not spec.get('subject'):
        return None
    if html is None:
        html = render_to_string(CORE_DEFAULT_HTML, context)
    text = _render_template(spec.get('template_text') or '', context) or strip_tags(html)
    subject = _render_subject(spec.get('subject') or '', context, notification.title)
    from_email = spec.get('from_email') or None
    return RenderedEmail(
        subject=subject,
        html_body=html,
        text_body=text,
        from_email=from_email,
        related_images=normalize_related_images(context.get('related_images')),
    )


def _apply_module_from_email(notification, rendered: RenderedEmail) -> RenderedEmail:
    if rendered.from_email:
        return rendered
    spec = _get_module_spec(notification)
    from_email = spec.get('from_email') if isinstance(spec, dict) else None
    if from_email:
        rendered.from_email = from_email
    return rendered


class EmailTemplateResolver:
    """Точка входа: resolve(notification) -> RenderedEmail."""

    @staticmethod
    def resolve(notification) -> RenderedEmail:
        context = _enrich_context(notification, build_base_email_context(notification))
        attachments = normalize_attachments(context.pop('attachments', None))

        rendered = _try_programmatic(notification, context)
        if rendered is not None:
            return _with_attachments(rendered, attachments)

        event_spec = catalog.get_event_spec(notification.source_module, notification.event_key)
        if event_spec is not None:
            email_spec = event_spec['channels'].get(catalog.CHANNEL_EMAIL) or {}
            if email_spec.get('template_html') or email_spec.get('subject'):
                rendered = _render_from_spec(email_spec, notification, context)
                if rendered is not None:
                    return _with_attachments(_apply_module_from_email(notification, rendered), attachments)

        module_spec = _get_module_spec(notification)
        if module_spec is not None:
            rendered = _render_from_spec(module_spec, notification, context)
            if rendered is not None:
                return _with_attachments(rendered, attachments)

        html = render_to_string(CORE_DEFAULT_HTML, context)
        text = _render_template(CORE_DEFAULT_TXT, context) or strip_tags(html)
        rendered = RenderedEmail(
            subject=notification.title,
            html_body=html,
            text_body=text,
            related_images=normalize_related_images(context.get('related_images')),
        )
        return _with_attachments(_apply_module_from_email(notification, rendered), attachments)
