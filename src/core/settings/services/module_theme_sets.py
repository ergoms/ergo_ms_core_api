"""Сборка и активация пар модульных тем (light + dark)."""

from __future__ import annotations

from src.core.settings.serializers import ThemeSerializer


def normalized_pair(value: str | None) -> str:
    text = (value or 'default').strip()
    return text or 'default'


def pair_queryset(queryset, module_key: str, module_pair: str):
    return queryset.filter(
        module_key=module_key,
        module_pair=normalized_pair(module_pair),
    )


def find_active_pair_name(queryset, module_key: str) -> str | None:
    active = queryset.filter(module_key=module_key, is_active=True)
    pairs = list(active.values_list('module_pair', flat=True).distinct())
    if not pairs:
        return None
    if len(pairs) > 1:
        # Неконсистентное состояние — берём первую пару
        return normalized_pair(pairs[0])
    return normalized_pair(pairs[0])


def find_default_pair_name(queryset, module_key: str) -> str | None:
    default = queryset.filter(module_key=module_key, is_default=True)
    pairs = list(default.values_list('module_pair', flat=True).distinct())
    if not pairs:
        return None
    return normalized_pair(pairs[0])


def build_module_theme_set(queryset, module_key: str, module_pair: str | None = None) -> dict | None:
    pair_name = normalized_pair(module_pair) if module_pair else find_active_pair_name(queryset, module_key)
    if not pair_name:
        pair_name = find_default_pair_name(queryset, module_key)
    if not pair_name:
        return None

    pair_qs = pair_queryset(queryset, module_key, pair_name)
    light_theme = pair_qs.filter(base_theme='light').first()
    dark_theme = pair_qs.filter(base_theme='dark').first()
    if not light_theme and not dark_theme:
        return None

    is_active = pair_qs.filter(is_active=True).exists()
    is_default = pair_qs.filter(is_default=True).exists()
    display_name = light_theme.name if light_theme else (dark_theme.name if dark_theme else pair_name)

    return {
        'module_key': module_key,
        'module_pair': pair_name,
        'name': display_name,
        'is_active': is_active,
        'is_default': is_default,
        'variants': {
            'light': ThemeSerializer(light_theme).data if light_theme else None,
            'dark': ThemeSerializer(dark_theme).data if dark_theme else None,
        },
    }


def activate_module_pair(theme_model, module_key: str, module_pair: str) -> dict | None:
    pair_name = normalized_pair(module_pair)
    theme_model.objects.filter(module_key=module_key).update(is_active=False)
    pair_queryset(theme_model.objects.all(), module_key, pair_name).update(is_active=True)
    return build_module_theme_set(theme_model.objects.all(), module_key, pair_name)


def list_module_pairs(queryset, module_key: str) -> list[dict]:
    pairs = (
        queryset.filter(module_key=module_key)
        .values_list('module_pair', flat=True)
        .distinct()
    )
    result = []
    seen = set()
    for raw_pair in pairs:
        pair_name = normalized_pair(raw_pair)
        if pair_name in seen:
            continue
        seen.add(pair_name)
        built = build_module_theme_set(queryset, module_key, pair_name)
        if built:
            result.append(built)
    return result
