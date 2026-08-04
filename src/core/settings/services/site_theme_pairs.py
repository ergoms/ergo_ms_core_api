"""Сборка пар палитр сайта (light + dark) по theme_pair.

Аналог module_theme_sets.py, но для тем сайта (module_key пуст). Тема без
theme_pair (кастомная, без связки) представляется как «пара из одного
варианта» — второй слот остаётся пустым.
"""

from __future__ import annotations

from src.core.settings.serializers import ThemeSerializer


def pair_key_for_theme(theme) -> str:
    """Ключ группировки: theme_pair или синтетический — для тем без пары."""
    key = (theme.theme_pair or '').strip()
    return key or f'theme-{theme.pk}'


def build_site_theme_pair(queryset, theme) -> dict:
    """Пара для конкретной темы сайта: light+dark по theme_pair, либо одиночный вариант."""
    key = (theme.theme_pair or '').strip()
    if key:
        pair_qs = queryset.filter(module_key__isnull=True, theme_pair=key)
        light = pair_qs.filter(base_theme='light').first()
        dark = pair_qs.filter(base_theme='dark').first()
    else:
        light = theme if theme.base_theme == 'light' else None
        dark = theme if theme.base_theme == 'dark' else None

    display_name = light.name if light else (dark.name if dark else theme.name)

    return {
        'pair_key': pair_key_for_theme(theme),
        'name': display_name,
        'is_default': bool((light and light.is_default) or (dark and dark.is_default)),
        'is_available': bool((light and light.is_available) or (dark and dark.is_available)),
        'is_system': bool((light and light.is_system) or (dark and dark.is_system)),
        'variants': {
            'light': ThemeSerializer(light).data if light else None,
            'dark': ThemeSerializer(dark).data if dark else None,
        },
    }


def list_site_theme_pairs(queryset) -> list[dict]:
    """Группирует темы сайта в пары для каталога быстрого выбора."""
    seen = set()
    result = []
    for theme in queryset.order_by('-is_default', '-is_system', 'name'):
        key = pair_key_for_theme(theme)
        if key in seen:
            continue
        seen.add(key)
        result.append(build_site_theme_pair(queryset, theme))
    return result
