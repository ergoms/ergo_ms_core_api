"""Каталог действий аудита.

Модули (и ядро) описывают человекочитаемые действия через multi-provider
группу `audit.action_definitions`:

    bridge.provide_many(
        'audit.action_definitions',
        key='<module>',
        obj={
            'module': '<module>',
            'module_label': 'Человекочитаемое имя',
            'actions': [
                {
                    'action': 'course.updated',
                    'label': 'Курс изменён',
                    'icon': 'BookOpen',            # Lucide, PascalCase (опц.)
                    'category': 'courses',          # опц.
                    'category_label': 'Курсы',      # опц.
                    'severity': 'info',             # info|security|critical (опц.)
                },
            ],
        },
    )

Каталог опционален: действие вне каталога отображается с generic-подписью.
Он нужен только чтобы лента выглядела красиво (label, иконка, важность).
"""

from __future__ import annotations

import logging

from src.core.integrations import bridge

logger = logging.getLogger('core.audit')

ACTION_DEFINITIONS_GROUP = 'audit.action_definitions'


def _normalize_action(raw: dict) -> dict | None:
    action = raw.get('action')
    if not action:
        return None
    return {
        'action': action,
        'label': raw.get('label') or action,
        'icon': raw.get('icon') or '',
        'category': raw.get('category') or '',
        'category_label': raw.get('category_label') or '',
        'severity': raw.get('severity') or 'info',
    }


def get_catalog() -> dict:
    """{module: {'module_label': str, 'actions': {action: spec}}}."""
    catalog: dict = {}
    for key, section in bridge.all(ACTION_DEFINITIONS_GROUP).items():
        if not isinstance(section, dict):
            logger.warning('Каталог аудита: секция %r не dict, пропуск', key)
            continue
        module = section.get('module') or key
        actions: dict = {}
        for raw in section.get('actions') or []:
            spec = _normalize_action(raw)
            if spec is None:
                logger.warning('Каталог аудита: действие без ключа в %r', module)
                continue
            actions[spec['action']] = spec
        catalog[module] = {
            'module': module,
            'module_label': section.get('module_label') or module,
            'actions': actions,
        }
    return catalog


def get_action_spec(source_module: str, action: str) -> dict | None:
    section = get_catalog().get(source_module or '')
    if not section:
        return None
    return section['actions'].get(action or '')


def get_flat_actions() -> list[dict]:
    """Плоский список действий для фильтров/подписей на клиенте."""
    result: list[dict] = []
    for section in get_catalog().values():
        for spec in section['actions'].values():
            result.append({
                'module': section['module'],
                'module_label': section['module_label'],
                **spec,
            })
    return result


def get_modules() -> list[dict]:
    """Список модулей-источников для фильтра."""
    return [
        {'module': section['module'], 'module_label': section['module_label']}
        for section in get_catalog().values()
    ]


def get_distinct_actors(limit: int = 500) -> list[dict]:
    """Уникальные инициаторы из журнала для фильтра UI.

    Привязанные пользователи — по public_id; «осиротевшие» записи — по actor_label.
    """
    from urllib.parse import quote

    from django.db.models import Max

    from .models import AuditEvent

    linked = (
        AuditEvent.objects
        .filter(actor_id__isnull=False, actor__public_id__isnull=False)
        .values('actor__public_id')
        .annotate(label=Max('actor_label'))
        .order_by('label')[:limit]
    )
    orphans = (
        AuditEvent.objects
        .filter(actor_id__isnull=True)
        .exclude(actor_label='')
        .values('actor_label')
        .distinct()
        .order_by('actor_label')
    )

    result: list[dict] = []
    for row in linked:
        public_id = row['actor__public_id']
        label = (row['label'] or '').strip() or str(public_id)
        result.append({'value': str(public_id), 'label': label})

    for row in orphans:
        label = (row['actor_label'] or '').strip()
        if not label:
            continue
        result.append({'value': f'label:{quote(label, safe="")}', 'label': label})

    result.sort(key=lambda item: item['label'].casefold())
    return result
