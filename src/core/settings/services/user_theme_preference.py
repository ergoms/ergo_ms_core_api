"""Личный выбор палитры и каталог быстрого выбора тем сайта."""

from __future__ import annotations

from django.db import transaction

from src.core.settings.models import Theme, UserThemePreference


def site_themes_qs():
    return Theme.objects.filter(module_key__isnull=True)


def get_site_default_theme() -> Theme | None:
    scope = site_themes_qs()
    return scope.filter(is_default=True).first() or scope.filter(is_active=True).first()


def get_or_create_preference(user) -> UserThemePreference:
    pref, _ = UserThemePreference.objects.get_or_create(user=user)
    return pref


def is_selectable_site_theme(theme: Theme | None) -> bool:
    if theme is None or theme.module_key:
        return False
    if theme.is_available:
        return True
    return bool(theme.is_default)


def get_effective_site_theme(user=None) -> Theme | None:
    """Палитра для пользователя: личный выбор (если доступен) или стандарт сайта."""
    if user is not None and getattr(user, 'is_authenticated', False):
        pref = (
            UserThemePreference.objects
            .select_related('selected_theme')
            .filter(user=user)
            .first()
        )
        selected = pref.selected_theme if pref else None
        if is_selectable_site_theme(selected):
            return selected
    return get_site_default_theme()


def preference_payload(user) -> dict:
    pref = get_or_create_preference(user)
    default_theme = get_site_default_theme()
    selected = pref.selected_theme
    if selected and not is_selectable_site_theme(selected):
        selected = None
    favorite_ids = list(
        pref.favorites.filter(module_key__isnull=True, is_available=True)
        .values_list('id', flat=True)
    )
    return {
        'selected_theme_id': selected.id if selected else None,
        'favorite_ids': favorite_ids,
        'default_theme_id': default_theme.id if default_theme else None,
    }


@transaction.atomic
def set_site_default_theme(theme: Theme) -> Theme:
    if theme.module_key:
        raise ValueError('Стандарт сайта задаётся только для тем сайта')
    Theme.objects.filter(module_key__isnull=True, is_default=True).exclude(pk=theme.pk).update(
        is_default=False,
    )
    Theme.objects.filter(module_key__isnull=True, is_active=True).exclude(pk=theme.pk).update(
        is_active=False,
    )
    theme.is_default = True
    theme.is_active = True
    theme.is_available = True
    theme.save(update_fields=['is_default', 'is_active', 'is_available', 'updated_at'])
    return theme


@transaction.atomic
def set_theme_available(theme: Theme, available: bool) -> Theme:
    if theme.module_key:
        raise ValueError('Каталог быстрого выбора — только для тем сайта')
    if not available and theme.is_default:
        raise ValueError('Нельзя убрать из каталога стандарт сайта. Сначала назначьте другой стандарт.')
    theme.is_available = available
    theme.save(update_fields=['is_available', 'updated_at'])
    if not available:
        UserThemePreference.objects.filter(selected_theme=theme).update(selected_theme=None)
        UserThemePreference.favorites.through.objects.filter(theme_id=theme.pk).delete()
    return theme


@transaction.atomic
def select_user_theme(user, theme_id) -> dict:
    pref = get_or_create_preference(user)
    if theme_id is None:
        pref.selected_theme = None
        pref.save(update_fields=['selected_theme', 'updated_at'])
        return preference_payload(user)

    try:
        theme = site_themes_qs().get(pk=theme_id)
    except Theme.DoesNotExist as exc:
        raise ValueError('Тема не найдена') from exc
    if not is_selectable_site_theme(theme):
        raise ValueError('Тема недоступна для выбора')
    pref.selected_theme = theme
    pref.save(update_fields=['selected_theme', 'updated_at'])
    return preference_payload(user)


@transaction.atomic
def update_user_favorites(user, *, add_id=None, remove_id=None) -> dict:
    pref = get_or_create_preference(user)
    if add_id is not None:
        try:
            theme = site_themes_qs().get(pk=add_id, is_available=True)
        except Theme.DoesNotExist as exc:
            raise ValueError('Тема недоступна для быстрого выбора') from exc
        pref.favorites.add(theme)
    if remove_id is not None:
        pref.favorites.remove(remove_id)
    return preference_payload(user)
