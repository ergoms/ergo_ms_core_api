"""Карточка человека: личность, которая не зависит от учётки и переживает её удаление."""

from __future__ import annotations

import logging
import uuid
from datetime import date

from django.contrib.auth import get_user_model
from django.db import transaction
from django.db.models import Q

from src.core.audit import core_actions
from src.core.audit.models import AuditEvent
from src.core.audit.service import AuditService
from src.core.cms.adp.models import UserProfile
from src.core.cms.adp.services import PermissionService
from src.core.integrations import bridge
from src.core.integrations.module_contracts import (
    CORE_PERSON_EDIT_POLICY,
    CORE_PERSON_LINKED,
    CORE_PERSON_MERGED,
    CORE_PERSON_UNLINKED,
)

from .models import Person, PersonAlias

logger = logging.getLogger(__name__)
User = get_user_model()

ALIAS_HOPS = 8
NAME_MAX = 150
NAME_FIELDS = ('last_name', 'first_name', 'middle_name')
NAMESAKES_LIMIT = 20
NAMESAKES_SCAN = 500
SIDE_PERSON = 'person'
SIDE_ACCOUNT = 'account'
SIDES = (SIDE_PERSON, SIDE_ACCOUNT)


class PersonError(Exception):
    """Отказ операции. code — машинный ключ, который модуль показывает или разбирает."""

    def __init__(self, code: str):
        super().__init__(code)
        self.code = code


def parse_uuid(raw) -> uuid.UUID | None:
    if raw in (None, ''):
        return None
    if isinstance(raw, uuid.UUID):
        return raw
    try:
        return uuid.UUID(str(raw))
    except (TypeError, ValueError, AttributeError):
        return None


def parse_date(raw) -> date | None:
    if raw in (None, ''):
        return None
    if isinstance(raw, date):
        return raw
    try:
        return date.fromisoformat(str(raw))
    except ValueError as exc:
        raise PersonError('invalid_birth_date') from exc


def fold(value) -> str:
    return str(value or '').strip().casefold().replace('ё', 'е')


def split_person_name(raw) -> tuple[str, str, str]:
    parts = str(raw or '').split()
    last_name = parts[0][:NAME_MAX] if parts else ''
    first_name = parts[1][:NAME_MAX] if len(parts) > 1 else ''
    middle_name = ' '.join(parts[2:])[:NAME_MAX] if len(parts) > 2 else ''
    return last_name, first_name, middle_name


def _clean_names(*, last_name='', first_name='', middle_name='', person_name='') -> dict:
    if person_name and not (last_name or first_name or middle_name):
        last_name, first_name, middle_name = split_person_name(person_name)
    return {
        'last_name': str(last_name or '').strip()[:NAME_MAX],
        'first_name': str(first_name or '').strip()[:NAME_MAX],
        'middle_name': str(middle_name or '').strip()[:NAME_MAX],
    }


def _account_names(user) -> dict:
    return {
        'last_name': str(user.last_name or '').strip()[:NAME_MAX],
        'first_name': str(user.first_name or '').strip()[:NAME_MAX],
        'middle_name': str(getattr(user, 'middle_name', '') or '').strip()[:NAME_MAX],
    }


def _own_names(person: Person) -> dict:
    return {field: str(getattr(person, field) or '').strip() for field in NAME_FIELDS}


def _account_birth_date(user) -> date | None:
    return (
        UserProfile.objects.filter(user_id=user.pk)
        .values_list('birth_date', flat=True)
        .first()
    )


def _user_by_public_id(raw):
    public_id = parse_uuid(raw)
    if public_id is None:
        return None
    return User.objects.filter(public_id=public_id).first()


# --- Ответ ---------------------------------------------------------------


def _payload(person: Person, account=None, account_birth: date | None = None) -> dict:
    if account is not None:
        names = _account_names(account)
        birth = account_birth
    else:
        names = _own_names(person)
        birth = person.birth_date
    return {
        'public_id': str(person.public_id),
        'user_public_id': str(person.user_public_id) if person.user_public_id else None,
        'linked': account is not None,
        **names,
        'full_name': ' '.join(names[field] for field in NAME_FIELDS if names[field]),
        'birth_date': birth.isoformat() if birth else None,
    }


def payloads(persons) -> dict[int, dict]:
    """Карточки пакетом: ФИО и дату рождения привязанных берём из учётки за два запроса."""
    persons = list(persons)
    user_ids = [person.user_public_id for person in persons if person.user_public_id]
    users = {}
    births = {}
    if user_ids:
        users = {user.public_id: user for user in User.objects.filter(public_id__in=user_ids)}
        births = dict(
            UserProfile.objects.filter(user_id__in=[user.pk for user in users.values()])
            .values_list('user_id', 'birth_date')
        )
    out = {}
    for person in persons:
        account = users.get(person.user_public_id) if person.user_public_id else None
        out[person.pk] = _payload(person, account, births.get(account.pk) if account else None)
    return out


def payload(person: Person) -> dict:
    return payloads([person])[person.pk]


# --- Поиск ---------------------------------------------------------------


def resolve(ref) -> Person | None:
    """Живая карточка по своему public_id или по public_id поглощённой карточки."""
    current = parse_uuid(ref)
    seen = set()
    for _ in range(ALIAS_HOPS):
        if current is None or current in seen:
            return None
        seen.add(current)
        person = Person.objects.filter(public_id=current).first()
        if person is not None:
            return person
        alias = (
            PersonAlias.objects.filter(loser_public_id=current)
            .select_related('survivor')
            .first()
        )
        if alias is None:
            return None
        current = alias.survivor.public_id
    return None


def resolve_many(refs) -> dict[str, dict]:
    parsed = {str(ref): parse_uuid(ref) for ref in (refs or [])}
    ids = {value for value in parsed.values() if value is not None}
    if not ids:
        return {}
    found = {person.public_id: person for person in Person.objects.filter(public_id__in=ids)}
    missing = ids - set(found)
    if missing:
        for alias in PersonAlias.objects.filter(loser_public_id__in=missing).select_related('survivor'):
            found[alias.loser_public_id] = alias.survivor
    unique = {person.pk: person for person in found.values()}
    rendered = payloads(unique.values())
    return {
        ref: rendered[found[value].pk]
        for ref, value in parsed.items()
        if value is not None and value in found
    }


def find_by_users(user_public_ids) -> dict[str, dict]:
    ids = {value for value in (parse_uuid(raw) for raw in (user_public_ids or [])) if value}
    if not ids:
        return {}
    persons = list(Person.objects.filter(user_public_id__in=ids))
    rendered = payloads(persons)
    return {str(person.user_public_id): rendered[person.pk] for person in persons}


def _names_match(candidate: dict, last: str, first: str, middle: str) -> bool:
    if fold(candidate['last_name']) != last or fold(candidate['first_name']) != first:
        return False
    other_middle = fold(candidate['middle_name'])
    return not (middle and other_middle) or middle[:1] == other_middle[:1]


def find_namesakes(*, last_name='', first_name='', middle_name='', person_name='', limit=NAMESAKES_LIMIT) -> list[dict]:
    """Однофамильцы: та же фамилия и имя, первая буква отчества, если она есть у обоих."""
    names = _clean_names(
        last_name=last_name,
        first_name=first_name,
        middle_name=middle_name,
        person_name=person_name,
    )
    last, first, middle = (fold(names[field]) for field in NAME_FIELDS)
    if not last or not first:
        return []
    variants = {names['last_name'], names['last_name'].replace('ё', 'е').replace('Ё', 'Е')}
    by_last = Q()
    for variant in variants:
        by_last |= Q(last_name__iexact=variant)
    linked_ids = list(
        User.objects.filter(by_last).values_list('public_id', flat=True)[:NAMESAKES_SCAN]
    )
    candidates = list(
        Person.objects.filter(
            (by_last & Q(user_public_id__isnull=True))
            | Q(user_public_id__in=[value for value in linked_ids if value])
        )[:NAMESAKES_SCAN]
    )
    rendered = payloads(candidates)
    matched = [
        rendered[person.pk]
        for person in candidates
        if _names_match(rendered[person.pk], last, first, middle)
    ]
    matched.sort(key=lambda item: (item['full_name'], item['public_id']))
    return matched[: max(1, int(limit or NAMESAKES_LIMIT))]


# --- Создание и правка ---------------------------------------------------


def ensure_for_user(user_public_id) -> Person:
    """Карточка учётки; если её ещё нет, создаётся со снимком ФИО и даты рождения."""
    public_id = parse_uuid(user_public_id)
    if public_id is None:
        raise PersonError('invalid_user')
    person = Person.objects.filter(user_public_id=public_id).first()
    if person is not None:
        return person
    user = User.objects.filter(public_id=public_id).first()
    if user is None:
        raise PersonError('user_not_found')
    person, _created = Person.objects.get_or_create(
        user_public_id=public_id,
        defaults={**_account_names(user), 'birth_date': _account_birth_date(user)},
    )
    return person


def create_unlinked(*, last_name='', first_name='', middle_name='', person_name='', birth_date=None) -> Person:
    names = _clean_names(
        last_name=last_name,
        first_name=first_name,
        middle_name=middle_name,
        person_name=person_name,
    )
    if not names['last_name'] and not names['first_name']:
        raise PersonError('name_required')
    return Person.objects.create(**names, birth_date=parse_date(birth_date))


def can_edit(user_public_id, person_public_id) -> bool:
    """Править ФИО можно только у карточки без учётки: у привязанной оно живёт в учётке."""
    person = resolve(person_public_id)
    if person is None or person.user_public_id:
        return False
    actor = _user_by_public_id(user_public_id)
    if actor is None:
        return False
    if PermissionService.is_admin(actor):
        return True
    for key, policy in (bridge.all(CORE_PERSON_EDIT_POLICY) or {}).items():
        if not callable(policy):
            continue
        try:
            verdict = policy(
                user_public_id=str(actor.public_id),
                person_public_id=str(person.public_id),
            )
        except Exception:
            logger.exception('person edit policy failed: key=%s', key)
            continue
        if verdict is True:
            return True
    return False


def update(person_public_id, *, actor_user_public_id, **fields) -> Person:
    person = resolve(person_public_id)
    if person is None:
        raise PersonError('person_not_found')
    if person.user_public_id:
        raise PersonError('person_linked')
    if not can_edit(actor_user_public_id, person.public_id):
        raise PersonError('forbidden')
    changes = []
    for field in NAME_FIELDS:
        if field not in fields:
            continue
        value = str(fields[field] or '').strip()[:NAME_MAX]
        if value != getattr(person, field):
            changes.append({'field': field, 'label': field, 'old': getattr(person, field), 'new': value})
            setattr(person, field, value)
    if 'birth_date' in fields:
        value = parse_date(fields['birth_date'])
        if value != person.birth_date:
            changes.append({
                'field': 'birth_date',
                'label': 'birth_date',
                'old': person.birth_date.isoformat() if person.birth_date else '',
                'new': value.isoformat() if value else '',
            })
            person.birth_date = value
    if not person.last_name and not person.first_name:
        raise PersonError('name_required')
    if changes:
        person.save()
        _audit(core_actions.PERSON_UPDATED, person, changes=changes, actor=_user_by_public_id(actor_user_public_id))
    return person


# --- Привязка, отвязка, слияние ------------------------------------------


def _require_admin(actor_user_public_id):
    actor = _user_by_public_id(actor_user_public_id)
    if actor is None or not PermissionService.is_admin(actor):
        raise PersonError('forbidden')
    return actor


def _names_differ(left: dict, right: dict) -> bool:
    if fold(left['last_name']) != fold(right['last_name']):
        return True
    if fold(left['first_name']) != fold(right['first_name']):
        return True
    left_middle, right_middle = fold(left['middle_name']), fold(right['middle_name'])
    return bool(left_middle and right_middle and left_middle != right_middle)


def _has_names(names: dict) -> bool:
    return bool(names['last_name'] or names['first_name'])


def _link_conflicts(person_names: dict, person_birth, account_names: dict, account_birth) -> dict:
    conflicts = {}
    if _has_names(person_names) and _has_names(account_names) and _names_differ(person_names, account_names):
        conflicts['names'] = {SIDE_PERSON: person_names, SIDE_ACCOUNT: account_names}
    if person_birth and account_birth and person_birth != account_birth:
        conflicts['birth_date'] = {
            SIDE_PERSON: person_birth.isoformat(),
            SIDE_ACCOUNT: account_birth.isoformat(),
        }
    return conflicts


def link(person_public_id, user_public_id, *, actor_user_public_id, names_from=None, birth_date_from=None) -> dict:
    """Явная привязка учётки. Расхождение ФИО или даты рождения без выбора стороны не пишется."""
    actor = _require_admin(actor_user_public_id)
    person = resolve(person_public_id)
    if person is None:
        raise PersonError('person_not_found')
    user = _user_by_public_id(user_public_id)
    if user is None:
        raise PersonError('user_not_found')
    if person.user_public_id == user.public_id:
        return {'status': 'linked', 'person': payload(person), 'merged_public_id': None}
    if person.user_public_id:
        raise PersonError('person_linked_to_other')

    account_names = _account_names(user)
    account_birth = _account_birth_date(user)
    person_names = _own_names(person)
    conflicts = _link_conflicts(person_names, person.birth_date, account_names, account_birth)
    unresolved = {}
    if 'names' in conflicts and names_from not in SIDES:
        unresolved['names'] = conflicts['names']
    if 'birth_date' in conflicts and birth_date_from not in SIDES:
        unresolved['birth_date'] = conflicts['birth_date']
    if unresolved:
        return {'status': 'conflict', 'conflicts': unresolved, 'person': payload(person)}

    other = Person.objects.filter(user_public_id=user.public_id).exclude(pk=person.pk).first()
    with transaction.atomic():
        merged_public_id = None
        if other is not None:
            merged_public_id = str(other.public_id)
            _merge(survivor=person, loser=other, actor=actor, emit_linked=False)
            person.refresh_from_db()
        else:
            person.user_public_id = user.public_id
            person.save(update_fields=['user_public_id', 'updated_at'])

        take_person_names = not _has_names(account_names) or (
            'names' in conflicts and names_from == SIDE_PERSON
        )
        if take_person_names and _has_names(person_names):
            name_updates = {field: person_names[field] for field in NAME_FIELDS}
        elif 'names' not in conflicts:
            name_updates = {
                field: person_names[field]
                for field in NAME_FIELDS
                if person_names[field] and not account_names[field]
            }
        else:
            name_updates = {}
        if name_updates:
            for field, value in name_updates.items():
                setattr(user, field, value)
            user.save(update_fields=list(name_updates))
        take_person_birth = person.birth_date and (
            not account_birth or ('birth_date' in conflicts and birth_date_from == SIDE_PERSON)
        )
        if take_person_birth:
            profile, _created = UserProfile.objects.get_or_create(user=user)
            profile.birth_date = person.birth_date
            profile.save(update_fields=['birth_date', 'updated_at'])

        _audit(core_actions.PERSON_LINKED, person, actor=actor, changes=[{
            'field': 'user_public_id',
            'label': 'Учётная запись',
            'old': '',
            'new': str(user.public_id),
        }], severity=AuditEvent.SEVERITY_SECURITY)
        bridge.emit(
            CORE_PERSON_LINKED,
            person_public_id=str(person.public_id),
            user_public_id=str(user.public_id),
        )
    return {'status': 'linked', 'person': payload(person), 'merged_public_id': merged_public_id}


def _snapshot_from_account(person: Person, user) -> None:
    names = _account_names(user)
    if _has_names(names):
        for field in NAME_FIELDS:
            setattr(person, field, names[field])
    birth = _account_birth_date(user)
    if birth:
        person.birth_date = birth


def _detach(person: Person, *, user=None, actor=None) -> Person:
    old = person.user_public_id
    if not old:
        return person
    account = user if user is not None else User.objects.filter(public_id=old).first()
    if account is not None:
        _snapshot_from_account(person, account)
    person.user_public_id = None
    person.save()
    _audit(core_actions.PERSON_UNLINKED, person, actor=actor, changes=[{
        'field': 'user_public_id',
        'label': 'Учётная запись',
        'old': str(old),
        'new': '',
    }], severity=AuditEvent.SEVERITY_SECURITY)
    bridge.emit(
        CORE_PERSON_UNLINKED,
        person_public_id=str(person.public_id),
        user_public_id=str(old),
    )
    return person


def unlink(person_public_id, *, actor_user_public_id) -> Person:
    actor = _require_admin(actor_user_public_id)
    person = resolve(person_public_id)
    if person is None:
        raise PersonError('person_not_found')
    with transaction.atomic():
        return _detach(person, actor=actor)


def detach_user(user) -> None:
    """Удаление учётки: карточка остаётся со снимком ФИО и даты рождения."""
    public_id = getattr(user, 'public_id', None)
    if not public_id:
        return
    person = Person.objects.filter(user_public_id=public_id).first()
    if person is None:
        return
    with transaction.atomic():
        _detach(person, user=user)


def _merge(*, survivor: Person, loser: Person, actor=None, emit_linked=True) -> Person:
    if survivor.pk == loser.pk:
        raise PersonError('same_person')
    if survivor.user_public_id and loser.user_public_id and survivor.user_public_id != loser.user_public_id:
        raise PersonError('both_linked')
    moved_user = None
    if loser.user_public_id and not survivor.user_public_id:
        moved_user = loser.user_public_id
        loser.user_public_id = None
        loser.save(update_fields=['user_public_id'])
        survivor.user_public_id = moved_user
    for field in NAME_FIELDS:
        if not str(getattr(survivor, field) or '').strip():
            setattr(survivor, field, getattr(loser, field))
    if survivor.birth_date is None:
        survivor.birth_date = loser.birth_date
    survivor.save()
    loser_public_id = loser.public_id
    PersonAlias.objects.filter(survivor=loser).update(survivor=survivor)
    PersonAlias.objects.update_or_create(loser_public_id=loser_public_id, defaults={'survivor': survivor})
    loser.delete()
    _audit(core_actions.PERSON_MERGED, survivor, actor=actor, meta={
        'loser_public_id': str(loser_public_id),
    }, severity=AuditEvent.SEVERITY_SECURITY)
    bridge.emit(
        CORE_PERSON_MERGED,
        survivor_public_id=str(survivor.public_id),
        loser_public_id=str(loser_public_id),
    )
    if moved_user and emit_linked:
        bridge.emit(
            CORE_PERSON_LINKED,
            person_public_id=str(survivor.public_id),
            user_public_id=str(moved_user),
        )
    return survivor


def merge(survivor_public_id, loser_public_id, *, actor_user_public_id) -> Person:
    actor = _require_admin(actor_user_public_id)
    survivor = resolve(survivor_public_id)
    loser = resolve(loser_public_id)
    if survivor is None or loser is None:
        raise PersonError('person_not_found')
    with transaction.atomic():
        return _merge(survivor=survivor, loser=loser, actor=actor)


def resolve_alias(ref) -> str | None:
    person = resolve(ref)
    return str(person.public_id) if person is not None else None


# --- Аудит ---------------------------------------------------------------


def _audit(action, person: Person, *, actor=None, changes=None, meta=None, severity=AuditEvent.SEVERITY_INFO) -> None:
    kwargs = {
        'action': action,
        'source_module': core_actions.MODULE,
        'entity': {'type': 'person', 'ref': str(person.public_id), 'label': str(person)},
        'changes': changes,
        'meta': meta,
        'severity': severity,
    }
    if actor is not None:
        kwargs['actor'] = actor
    try:
        AuditService.record(**kwargs)
    except Exception:
        logger.exception('person audit failed: action=%s person=%s', action, person.public_id)
