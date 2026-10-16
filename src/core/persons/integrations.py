"""Операции карточки человека в ModuleBridge.

Модули хранят person_public_id и работают с карточкой только через эти операции.
Kwargs и ответы — JSON-примитивы, чтобы вызов проходил и через HTTP-мост.
Отказ операции, которая меняет карточку, — {'status': 'error', 'error': код}.
"""

from src.core.integrations import bridge
from src.core.integrations.module_contracts import (
    CORE_PERSON_CAN_EDIT,
    CORE_PERSON_CREATE_UNLINKED,
    CORE_PERSON_ENSURE_FOR_USER,
    CORE_PERSON_FIND_BY_USERS,
    CORE_PERSON_FIND_NAMESAKES,
    CORE_PERSON_GET,
    CORE_PERSON_LINK,
    CORE_PERSON_MERGE,
    CORE_PERSON_RESOLVE_ALIAS,
    CORE_PERSON_RESOLVE_MANY,
    CORE_PERSON_UNLINK,
    CORE_PERSON_UPDATE,
)

from . import service
from .service import PersonError


def _error(exc: PersonError) -> dict:
    return {'status': 'error', 'error': exc.code}


def _ok(person) -> dict:
    return {'status': 'ok', 'person': service.payload(person)}


@bridge.provide_op(CORE_PERSON_ENSURE_FOR_USER)
def _ensure_for_user(*, user_public_id, **_):
    try:
        return service.payload(service.ensure_for_user(user_public_id))
    except PersonError:
        return None


@bridge.provide_op(CORE_PERSON_GET)
def _get(*, person_public_id, **_):
    person = service.resolve(person_public_id)
    return service.payload(person) if person is not None else None


@bridge.provide_op(CORE_PERSON_RESOLVE_MANY)
def _resolve_many(*, person_public_ids, **_):
    return service.resolve_many(person_public_ids)


@bridge.provide_op(CORE_PERSON_FIND_BY_USERS)
def _find_by_users(*, user_public_ids, **_):
    return service.find_by_users(user_public_ids)


@bridge.provide_op(CORE_PERSON_CREATE_UNLINKED)
def _create_unlinked(*, last_name='', first_name='', middle_name='', person_name='', birth_date=None, **_):
    try:
        return _ok(service.create_unlinked(
            last_name=last_name,
            first_name=first_name,
            middle_name=middle_name,
            person_name=person_name,
            birth_date=birth_date,
        ))
    except PersonError as exc:
        return _error(exc)


@bridge.provide_op(CORE_PERSON_FIND_NAMESAKES)
def _find_namesakes(*, last_name='', first_name='', middle_name='', person_name='', limit=None, **_):
    return service.find_namesakes(
        last_name=last_name,
        first_name=first_name,
        middle_name=middle_name,
        person_name=person_name,
        limit=limit or service.NAMESAKES_LIMIT,
    )


@bridge.provide_op(CORE_PERSON_UPDATE)
def _update(*, person_public_id, actor_user_public_id, **fields):
    allowed = {key: value for key, value in fields.items() if key in (*service.NAME_FIELDS, 'birth_date')}
    try:
        return _ok(service.update(person_public_id, actor_user_public_id=actor_user_public_id, **allowed))
    except PersonError as exc:
        return _error(exc)


@bridge.provide_op(CORE_PERSON_LINK)
def _link(*, person_public_id, user_public_id, actor_user_public_id, names_from=None, birth_date_from=None, **_):
    try:
        return service.link(
            person_public_id,
            user_public_id,
            actor_user_public_id=actor_user_public_id,
            names_from=names_from,
            birth_date_from=birth_date_from,
        )
    except PersonError as exc:
        return _error(exc)


@bridge.provide_op(CORE_PERSON_UNLINK)
def _unlink(*, person_public_id, actor_user_public_id, **_):
    try:
        return _ok(service.unlink(person_public_id, actor_user_public_id=actor_user_public_id))
    except PersonError as exc:
        return _error(exc)


@bridge.provide_op(CORE_PERSON_MERGE)
def _merge(*, survivor_public_id, loser_public_id, actor_user_public_id, **_):
    try:
        return _ok(service.merge(
            survivor_public_id,
            loser_public_id,
            actor_user_public_id=actor_user_public_id,
        ))
    except PersonError as exc:
        return _error(exc)


@bridge.provide_op(CORE_PERSON_RESOLVE_ALIAS)
def _resolve_alias(*, person_public_id, **_):
    return service.resolve_alias(person_public_id)


@bridge.provide_op(CORE_PERSON_CAN_EDIT)
def _can_edit(*, user_public_id, person_public_id, **_):
    return service.can_edit(user_public_id, person_public_id)
