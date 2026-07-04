"""
Расширения стандартной модели django.contrib.auth.models.User.

Поля middle_name и public_id живут в auth_user (миграция cms_adp.0038).
ORM-поля и методы подключаются при старте приложения — без форка Django.
"""

from __future__ import annotations

import uuid

from django.contrib.auth.models import User
from django.db import models

_USER_EXTENSIONS_APPLIED = False


def ergo_get_full_name(user: User) -> str:
    """Формат: «Фамилия Имя Отчество»."""
    name_parts = [user.last_name, user.first_name]
    middle_name = getattr(user, 'middle_name', None)
    if middle_name:
        name_parts.append(middle_name)

    full_name = ' '.join(part for part in name_parts if part and str(part).strip())
    return full_name.strip() or user.username or user.email


def ergo_get_initials_name(user: User) -> str:
    """Формат: «Фамилия И.О.»."""
    last_name = (user.last_name or '').strip()
    first_name = (user.first_name or '').strip()
    middle_name = (getattr(user, 'middle_name', '') or '').strip()

    initials_parts = []
    if first_name:
        initials_parts.append(f'{first_name[0].upper()}.')
    if middle_name:
        initials_parts.append(f'{middle_name[0].upper()}.')

    initials_block = ''.join(initials_parts)

    if last_name:
        if initials_block:
            return f'{last_name} {initials_block}'
        return last_name

    return initials_block or user.username


def apply_user_extensions() -> None:
    """Подключает поля и методы к стандартной модели User (идемпотентно)."""
    global _USER_EXTENSIONS_APPLIED
    if _USER_EXTENSIONS_APPLIED:
        return

    if not hasattr(User, 'middle_name'):
        models.CharField(
            verbose_name='middle name',
            max_length=150,
            blank=True,
            null=True,
        ).contribute_to_class(User, 'middle_name')

    if not hasattr(User, 'public_id'):
        models.UUIDField(
            verbose_name='public id',
            default=uuid.uuid4,
            unique=True,
            null=True,
            editable=False,
        ).contribute_to_class(User, 'public_id')

    User.get_full_name = ergo_get_full_name
    User.get_initials_name = ergo_get_initials_name

    _USER_EXTENSIONS_APPLIED = True
