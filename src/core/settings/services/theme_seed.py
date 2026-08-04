from django.core.exceptions import FieldDoesNotExist

from src.core.settings.services.theme_seed_catalog import (
    ACCESSIBILITY_THEME_BASE_NAMES,
    ACCESSIBILITY_THEME_RENAME_MAP,
    DEFAULT_THEME_COLORS,
    SYSTEM_THEME_RENAME_MAP,
    SYSTEM_THEMES,
    derive_site_theme_pair_key,
    is_accessibility_theme,
)

__all__ = [
    "ACCESSIBILITY_THEME_BASE_NAMES",
    "ACCESSIBILITY_THEME_RENAME_MAP",
    "DEFAULT_THEME_COLORS",
    "SYSTEM_THEME_RENAME_MAP",
    "SYSTEM_THEMES",
    "derive_site_theme_pair_key",
    "ensure_module_themes_from_manifests",
    "ensure_system_themes",
    "is_accessibility_theme",
    "rename_system_themes",
    "reset_module_theme_from_snapshot",
    "reset_system_theme_to_defaults",
]


def _model_has_field(model, field_name):
    try:
        model._meta.get_field(field_name)
        return True
    except FieldDoesNotExist:
        return False


def _colors_for_spec(spec):
    if spec.get('colors'):
        return dict(spec['colors'])
    return dict(DEFAULT_THEME_COLORS[spec['base_theme']])


def _system_spec_for_theme(theme):
    for spec in SYSTEM_THEMES:
        if theme.name == spec['name']:
            return spec
    return None


def reset_system_theme_to_defaults(theme):
    """Сбрасывает одну системную тему к начальным значениям."""
    if not theme.is_system:
        return False

    spec = _system_spec_for_theme(theme)
    if spec is None:
        return False

    theme.description = spec['description']
    theme.colors = _colors_for_spec(spec)
    theme.bootstrap_colors = {}
    update_fields = ['description', 'colors', 'bootstrap_colors', 'updated_at']
    if _model_has_field(type(theme), 'theme_pair'):
        theme.theme_pair = derive_site_theme_pair_key(theme.name)
        update_fields.append('theme_pair')
    theme.save(update_fields=update_fields)
    return True


def _site_system_themes_qs(theme_model, **filters):
    qs = theme_model.objects.filter(is_system=True, **filters)
    if _model_has_field(theme_model, 'module_key'):
        qs = qs.filter(module_key__isnull=True)
    return qs


def _pick_canonical_theme(themes):
    """Активная → default → меньший pk."""
    return sorted(
        themes,
        key=lambda theme: (not theme.is_active, not theme.is_default, theme.pk),
    )[0]


def _merge_theme_flags(keeper, duplicate):
    changed = False
    if duplicate.is_active and not keeper.is_active:
        keeper.is_active = True
        changed = True
    if duplicate.is_default and not keeper.is_default:
        keeper.is_default = True
        changed = True
    return changed


def _dedupe_system_themes_by_name(theme_model, name):
    """Оставляет одну системную тему сайта с данным именем, лишние удаляет."""
    existing = list(_site_system_themes_qs(theme_model, name=name).order_by('pk'))
    if len(existing) <= 1:
        return existing[0] if existing else None

    keeper = _pick_canonical_theme(existing)
    flags_changed = False
    for duplicate in existing:
        if duplicate.pk == keeper.pk:
            continue
        flags_changed = _merge_theme_flags(keeper, duplicate) or flags_changed
        duplicate.delete()

    if flags_changed:
        keeper.save(update_fields=['is_active', 'is_default', 'updated_at'])
    return keeper


def rename_system_themes(theme_model, rename_map, *, descriptions=None):
    """
    Переименовывает системные темы сайта без дубликатов по имени.

    Если целевое имя уже есть — переносит флаги active/default и удаляет старую запись.
    """
    descriptions = descriptions or {}
    themes = list(_site_system_themes_qs(theme_model).order_by('pk'))

    for theme in themes:
        new_name = rename_map.get(theme.name)
        if not new_name or new_name == theme.name:
            continue

        # Тема могла быть удалена как дубликат на предыдущей итерации.
        if not _site_system_themes_qs(theme_model, pk=theme.pk).exists():
            continue

        targets = list(
            _site_system_themes_qs(theme_model, name=new_name).exclude(pk=theme.pk)
        )
        if targets:
            keeper = _pick_canonical_theme(targets)
            flags_changed = _merge_theme_flags(keeper, theme)
            if flags_changed:
                keeper.save(update_fields=['is_active', 'is_default', 'updated_at'])
            theme.delete()
            continue

        theme.name = new_name
        update_fields = ['name', 'updated_at']
        if new_name in descriptions:
            theme.description = descriptions[new_name]
            update_fields.insert(1, 'description')
        theme.save(update_fields=update_fields)

    # На случай уже существующих дублей с одинаковым именем.
    for name in {spec['name'] for spec in SYSTEM_THEMES}:
        _dedupe_system_themes_by_name(theme_model, name)


def ensure_system_themes(theme_model, *, update_existing=False):
    """Создаёт системные темы сайта, если их ещё нет (идемпотентно при дублях)."""
    created = []
    updated = []

    for spec in SYSTEM_THEMES:
        defaults = {
            'description': spec['description'],
            'author': 'System',
            'base_theme': spec['base_theme'],
            'colors': _colors_for_spec(spec),
            'bootstrap_colors': {},
            'is_active': False,
            'is_default': spec['is_default'],
        }
        if _model_has_field(theme_model, 'theme_pair'):
            defaults['theme_pair'] = derive_site_theme_pair_key(spec['name'])
        theme = _dedupe_system_themes_by_name(theme_model, spec['name'])
        if theme is None:
            create_kwargs = {
                'name': spec['name'],
                'is_system': True,
                **defaults,
            }
            if _model_has_field(theme_model, 'module_key'):
                create_kwargs['module_key'] = None
            theme = theme_model.objects.create(**create_kwargs)
            created.append(theme)
            continue
        if not update_existing:
            continue
        reset_system_theme_to_defaults(theme)
        updated.append(theme)

    return created, updated


def _normalize_manifest(manifest):
    module_key = manifest.get('moduleKey') or manifest.get('module_key')
    if not module_key:
        return None
    return {
        'module_key': module_key,
        'display_name': manifest.get('displayName') or manifest.get('display_name') or module_key,
        'base_theme': manifest.get('baseTheme') or manifest.get('base_theme') or 'light',
        'colors': manifest.get('colors') or {},
        'bootstrap_colors': manifest.get('bootstrap_colors') or manifest.get('bootstrapColors') or {},
        'module_pair': manifest.get('modulePair') or manifest.get('module_pair') or 'default',
        'module_tokens': manifest.get('moduleTokens') or manifest.get('module_tokens') or {},
        'system_themes': manifest.get('systemThemes') or manifest.get('system_themes'),
    }


def _module_system_specs(manifest):
    specs = manifest.get('system_themes')
    if specs:
        return specs
    display = manifest['display_name']
    base = manifest['base_theme']
    return (
        {
            'name': f'Системная ({display})',
            'description': f'Системная тема модуля {display}',
            'base_theme': base,
            'is_default': True,
            'colors': manifest['colors'],
            'module_pair': manifest.get('module_pair', 'default'),
            'module_tokens': manifest['module_tokens'],
        },
        {
            'name': f'Системная ({display})',
            'description': f'Системная тема модуля {display}',
            'base_theme': 'dark' if base == 'light' else 'light',
            'is_default': True,
            'colors': DEFAULT_THEME_COLORS['dark' if base == 'light' else 'light'],
            'module_pair': manifest.get('module_pair', 'default'),
            'module_tokens': manifest['module_tokens'],
        },
    )


def _build_theme_defaults_snapshot(manifest, spec, *, colors, module_tokens):
    return {
        'moduleKey': manifest['module_key'],
        'modulePair': spec.get('module_pair') or manifest.get('module_pair') or 'default',
        'baseTheme': spec['base_theme'],
        'colors': colors,
        'bootstrap_colors': manifest['bootstrap_colors'],
        'moduleTokens': module_tokens,
        'name': spec['name'],
        'description': spec.get('description', ''),
    }


def reset_module_theme_from_snapshot(theme):
    """Сбрасывает модульную системную тему к snapshot из sync-module-defaults."""
    snapshot = theme.defaults_snapshot or {}
    if not snapshot:
        return False

    theme.description = snapshot.get('description') or theme.description
    theme.colors = snapshot.get('colors') or {}
    theme.bootstrap_colors = snapshot.get('bootstrap_colors') or {}
    theme.module_tokens = snapshot.get('moduleTokens') or snapshot.get('module_tokens') or {}
    if snapshot.get('name'):
        theme.name = snapshot['name']
    theme.save(
        update_fields=[
            'description', 'colors', 'bootstrap_colors', 'module_tokens', 'name', 'updated_at',
        ]
    )
    return True


def ensure_module_themes_from_manifests(theme_model, manifests, *, update_existing=False):
    """Создаёт/обновляет системные темы модулей из manifest (клиент theme-defaults.js)."""
    created = []
    updated = []

    for raw in manifests:
        manifest = _normalize_manifest(raw)
        if manifest is None:
            continue

        for spec in _module_system_specs(manifest):
            colors = spec.get('colors') or manifest['colors'] or DEFAULT_THEME_COLORS.get(
                spec['base_theme'], DEFAULT_THEME_COLORS['light']
            )
            module_tokens = spec.get('module_tokens') or manifest['module_tokens'] or {}
            snapshot = _build_theme_defaults_snapshot(
                manifest,
                spec,
                colors=colors,
                module_tokens=module_tokens,
            )
            defaults = {
                'description': spec.get('description', ''),
                'author': 'System',
                'base_theme': spec['base_theme'],
                'module_key': manifest['module_key'],
                'module_pair': spec.get('module_pair') or manifest.get('module_pair') or 'default',
                'colors': colors,
                'bootstrap_colors': manifest['bootstrap_colors'],
                'module_tokens': module_tokens,
                'defaults_snapshot': snapshot,
                'is_active': False,
                'is_default': spec.get('is_default', False),
            }
            theme, was_created = theme_model.objects.get_or_create(
                module_key=manifest['module_key'],
                module_pair=defaults['module_pair'],
                base_theme=spec['base_theme'],
                is_system=True,
                defaults={**defaults, 'name': spec['name']},
            )
            if was_created:
                created.append(theme)
                continue
            if not update_existing:
                continue
            theme.description = defaults['description']
            theme.colors = defaults['colors']
            theme.bootstrap_colors = defaults['bootstrap_colors']
            theme.module_tokens = defaults['module_tokens']
            theme.base_theme = defaults['base_theme']
            theme.module_pair = defaults['module_pair']
            theme.name = spec['name']
            theme.defaults_snapshot = snapshot
            theme.save(
                update_fields=[
                    'description', 'colors', 'bootstrap_colors',
                    'module_tokens', 'base_theme', 'module_pair', 'name',
                    'defaults_snapshot', 'updated_at',
                ]
            )
            updated.append(theme)

    return created, updated
