"""Портрет карточки человека. Пока учётка привязана, на экране аватар аккаунта."""

from __future__ import annotations

import logging

from rest_framework.exceptions import ValidationError

from src.core.audit.models import AuditEvent
from src.core.utils.media_client import get_media_client
from src.core.utils.media_signing import get_signed_media_url
from src.core.utils.mixins import validate_media_path

logger = logging.getLogger(__name__)

PORTRAIT_PREFIX = 'avatars/persons'
PORTRAIT_SUFFIXES = ('.jpg', '.jpeg', '.png', '.webp', '.gif')


def portrait_dir(person_public_id) -> str:
    return f'{PORTRAIT_PREFIX}/{person_public_id}'


def portrait_url(person, *, linked: bool) -> str | None:
    """Подписанный адрес. У привязанной карточки пусто: кружок берёт аватар учётки."""
    if linked or not (getattr(person, 'avatar_path', None) or '').strip():
        return None
    return get_signed_media_url(person.avatar_path.strip())


def drop_portrait_file(path: str) -> None:
    stored = (path or '').strip()
    if not stored:
        return
    try:
        get_media_client().delete(stored)
    except Exception:
        logger.warning('Не удалось удалить портрет карточки человека', exc_info=True)


def validate_portrait_path(file_path, person_public_id) -> str:
    from .service import PersonError

    try:
        stored = validate_media_path(file_path, 'file_path')
    except ValidationError as exc:
        raise PersonError('invalid_portrait') from exc
    normalized = stored.replace('\\', '/').lstrip('/')
    expected = portrait_dir(person_public_id)
    if normalized != expected and not normalized.startswith(f'{expected}/'):
        raise PersonError('invalid_portrait')
    if not normalized.lower().endswith(PORTRAIT_SUFFIXES):
        raise PersonError('invalid_portrait')
    return normalized


def absorb_portrait(survivor, loser) -> None:
    """Пустой портрет выжившей карточки забирает файл поглощённой. Второй файл удаляется."""
    survivor_path = (survivor.avatar_path or '').strip()
    loser_path = (loser.avatar_path or '').strip()
    if not loser_path:
        return
    if not survivor_path:
        survivor.avatar_path = loser_path
        loser.avatar_path = ''
        return
    if loser_path != survivor_path:
        drop_portrait_file(loser_path)
    loser.avatar_path = ''


def _editable_person(person_public_id, actor_user_public_id):
    from . import service

    actor = service._require_admin(actor_user_public_id)
    person = service.resolve(person_public_id)
    if person is None:
        raise service.PersonError('person_not_found')
    if person.user_public_id:
        raise service.PersonError('person_linked')
    return service, actor, person


def set_portrait(person_public_id, file_path, *, actor_user_public_id):
    from src.core.audit import core_actions

    service, actor, person = _editable_person(person_public_id, actor_user_public_id)
    stored = validate_portrait_path(file_path, person.public_id)
    previous = (person.avatar_path or '').strip()
    if previous == stored:
        return person
    person.avatar_path = stored
    person.save(update_fields=['avatar_path', 'updated_at'])
    if previous:
        drop_portrait_file(previous)
    service._audit(
        core_actions.PERSON_UPDATED,
        person,
        actor=actor,
        changes=[{
            'field': 'avatar_path',
            'label': 'avatar_path',
            'old': previous,
            'new': stored,
        }],
        severity=AuditEvent.SEVERITY_INFO,
    )
    return person


def clear_portrait(person_public_id, *, actor_user_public_id):
    from src.core.audit import core_actions

    service, actor, person = _editable_person(person_public_id, actor_user_public_id)
    previous = (person.avatar_path or '').strip()
    if not previous:
        return person
    person.avatar_path = ''
    person.save(update_fields=['avatar_path', 'updated_at'])
    drop_portrait_file(previous)
    service._audit(
        core_actions.PERSON_UPDATED,
        person,
        actor=actor,
        changes=[{
            'field': 'avatar_path',
            'label': 'avatar_path',
            'old': previous,
            'new': '',
        }],
        severity=AuditEvent.SEVERITY_INFO,
    )
    return person