"""
Утилиты токенизированного поиска пользователей.

Каждое слово из строки поиска должно совпасть хотя бы с одним из полей (AND между словами, OR между полями).
"""

from django.contrib.auth import get_user_model
from django.db.models import Q

User = get_user_model()

DEFAULT_USER_SEARCH_FIELDS = (
    'username',
    'email',
    'first_name',
    'last_name',
    'middle_name',
)


def tokenize_search(search: str) -> list[str]:
    normalized = (search or '').strip()
    if not normalized:
        return []
    return [token for token in normalized.split() if token]


def build_user_token_q(
    token: str,
    *,
    prefix: str = '',
    fields: tuple[str, ...] = DEFAULT_USER_SEARCH_FIELDS,
    extra_fields: tuple[str, ...] = (),
) -> Q:
    token_filter = Q()
    for field in fields:
        token_filter |= Q(**{f'{prefix}{field}__icontains': token})
    for field in extra_fields:
        token_filter |= Q(**{f'{field}__icontains': token})
    return token_filter


def apply_user_search(
    queryset,
    search: str,
    *,
    prefix: str = '',
    fields: tuple[str, ...] = DEFAULT_USER_SEARCH_FIELDS,
    extra_fields: tuple[str, ...] = (),
):
    tokens = tokenize_search(search)
    if not tokens:
        return queryset

    for token in tokens:
        queryset = queryset.filter(
            build_user_token_q(
                token,
                prefix=prefix,
                fields=fields,
                extra_fields=extra_fields,
            )
        )

    return queryset


def build_user_search_q(
    search: str,
    *,
    prefix: str = '',
    fields: tuple[str, ...] = DEFAULT_USER_SEARCH_FIELDS,
    extra_fields: tuple[str, ...] = (),
) -> Q:
    tokens = tokenize_search(search)
    if not tokens:
        return Q()

    combined = Q()
    for token in tokens:
        combined &= build_user_token_q(
            token,
            prefix=prefix,
            fields=fields,
            extra_fields=extra_fields,
        )
    return combined


def resolve_user_by_search(search: str, *, queryset=None):
    normalized = (search or '').strip()
    if not normalized:
        return None

    base_qs = queryset if queryset is not None else User.objects.all()

    exact = base_qs.filter(username=normalized).first()
    if exact:
        return exact

    return apply_user_search(base_qs, normalized).first()
