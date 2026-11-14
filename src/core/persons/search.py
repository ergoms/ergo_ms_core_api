"""Поиск карточек людей по строке для окон выбора человека."""

from __future__ import annotations

from django.contrib.auth import get_user_model
from django.db.models import Q

from src.core.cms.adp.services.user_search import apply_user_search

from .models import Person
from .service import payloads

User = get_user_model()

SEARCH_LIMIT = 30


def search(query, *, limit=SEARCH_LIMIT) -> list[dict]:
    """Карточки по строке: ФИО карточек без учётки и учётки через поиск пользователей.

    Каждое слово строки должно найтись в фамилии, имени или отчестве карточки.
    Учётку без карточки поиск не заводит: у неё в ответе пустой public_id.
    """
    text = str(query or '').strip()
    limit = max(1, min(int(limit or SEARCH_LIMIT), SEARCH_LIMIT))
    if len(text) < 2:
        return []
    unlinked = Q(user_public_id__isnull=True)
    for word in text.split()[:4]:
        unlinked &= Q(last_name__icontains=word) | Q(first_name__icontains=word) | Q(middle_name__icontains=word)
    persons = list(Person.objects.filter(unlinked).order_by('last_name', 'first_name', 'middle_name')[:limit])
    users = list(apply_user_search(User.objects.filter(is_active=True), text)[:limit])
    linked = {person.user_public_id: person for person in Person.objects.filter(user_public_id__in=[user.public_id for user in users])}
    rendered = payloads([*persons, *linked.values()])
    out = [rendered[person.pk] for person in persons]
    for user in users:
        person = linked.get(user.public_id)
        card = dict(rendered[person.pk]) if person else {
            'public_id': None,
            'user_public_id': str(user.public_id),
            'linked': True,
            'full_name': (user.get_full_name() or user.username or '').strip(),
            'avatar_url': '',
        }
        card['email'] = user.email or ''
        out.append(card)
    out.sort(key=lambda item: (not item.get('linked'), (item.get('full_name') or '').casefold()))
    return out[:limit]
