"""
Каталог настраиваемых событий уведомлений.

Модули регистрируют свои секции через multi-provider группу
`notifications.event_definitions`:

    bridge.provide_many(
        'notifications.event_definitions',
        key='<module>',
        obj={
            'module': '<module>',
            'module_label': 'Человекочитаемое имя',
            'events': [
                {
                    'event_key': '...',
                    'label': '...',
                    'category': '...',            # опционально
                    'category_label': '...',      # опционально
                    'channels': {
                        'in_app': {'available': True, 'default': True},
                        'email': {
                            'available': True,
                            'default': True,
                            'subject': '...',           # Django template string
                            'template_html': '...',     # путь Django-шаблона
                            'template_text': '...',
                        },
                    },
                },
            ],
        },
    )

Каталог — единственный источник истины для UI панели настроек и для
дефолтов PreferenceResolver.
"""

import logging

from src.core.integrations import bridge

logger = logging.getLogger('core.notifications')

EVENT_DEFINITIONS_GROUP = 'notifications.event_definitions'

CHANNEL_IN_APP = 'in_app'
CHANNEL_EMAIL = 'email'
CHANNELS = (CHANNEL_IN_APP, CHANNEL_EMAIL)

# Событие не описано в каталоге: in_app шлём (обратная совместимость),
# email — нет (письма только для явно задекларированных событий).
FALLBACK_CHANNEL_DEFAULTS = {
    CHANNEL_IN_APP: {'available': True, 'default': True},
    CHANNEL_EMAIL: {'available': False, 'default': False},
}


def _normalize_channel_spec(raw):
    if not isinstance(raw, dict):
        return {'available': False, 'default': False}
    return {
        'available': bool(raw.get('available', False)),
        'default': bool(raw.get('default', False)),
        'subject': raw.get('subject') or '',
        'template_html': raw.get('template_html') or '',
        'template_text': raw.get('template_text') or '',
    }


def _normalize_event(raw):
    event_key = raw.get('event_key')
    if not event_key:
        return None
    channels_raw = raw.get('channels') or {}
    return {
        'event_key': event_key,
        'label': raw.get('label') or event_key,
        'category': raw.get('category') or '',
        'category_label': raw.get('category_label') or '',
        'channels': {
            channel: _normalize_channel_spec(channels_raw.get(channel))
            for channel in CHANNELS
        },
    }


def get_catalog() -> dict:
    """Агрегированный каталог: {module: {'module_label': str, 'events': {event_key: spec}}}.

    bridge.all() при LocalTransport — in-memory, кеширование не требуется.
    """
    catalog = {}
    for key, section in bridge.all(EVENT_DEFINITIONS_GROUP).items():
        if not isinstance(section, dict):
            logger.warning('Каталог уведомлений: секция %r не dict, пропуск', key)
            continue
        module = section.get('module') or key
        events = {}
        for raw in section.get('events') or []:
            event = _normalize_event(raw)
            if event is None:
                logger.warning('Каталог уведомлений: событие без event_key в %r', module)
                continue
            events[event['event_key']] = event
        catalog[module] = {
            'module': module,
            'module_label': section.get('module_label') or module,
            'events': events,
        }
    return catalog


def get_event_spec(source_module: str, event_key: str) -> dict | None:
    section = get_catalog().get(source_module or '')
    if not section:
        return None
    return section['events'].get(event_key or '')


def get_channel_defaults(source_module: str, event_key: str) -> dict:
    """Возвращает {channel: {'available': bool, 'default': bool}} для события.

    Для событий вне каталога — FALLBACK_CHANNEL_DEFAULTS.
    """
    spec = get_event_spec(source_module, event_key)
    if spec is None:
        return FALLBACK_CHANNEL_DEFAULTS
    return spec['channels']
