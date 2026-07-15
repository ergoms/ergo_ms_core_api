from django.core.exceptions import FieldDoesNotExist


def _model_has_field(model, field_name):
    try:
        model._meta.get_field(field_name)
        return True
    except FieldDoesNotExist:
        return False


DEFAULT_THEME_COLORS = {
    'light': {
        'headerBackground': 'rgba(255, 255, 255, 0.85)',
        'authBackground': 'rgba(255, 255, 255, 0.7)',
        'background': '#f2f2f2',
        'border': '#e0e0e0',
        'primaryText': '#101223',
        'secondaryText': '#6e6e6e',
        'primaryBackground': '#ffffff',
        'secondaryBackground': '#f1f1f1',
        'hoverBackground': '#e1e1e1',
        'accent': '#d0322d',
    },
    'dark': {
        'headerBackground': 'rgba(30, 30, 30, 0.85)',
        'authBackground': 'rgba(30, 30, 30, 0.7)',
        'background': '#111112',
        'border': '#555555',
        'primaryText': '#c9cccf',
        'secondaryText': '#6e6e6e',
        'primaryBackground': '#18181a',
        'secondaryBackground': '#2a2a2c',
        'hoverBackground': '#3d3d3f',
        'accent': '#f14336',
    },
}

SYSTEM_THEMES = (
    {
        'name': 'Светлая',
        'description': 'Системная светлая тема',
        'base_theme': 'light',
        'is_default': True,
    },
    {
        'name': 'Тёмная',
        'description': 'Системная тёмная тема',
        'base_theme': 'dark',
        'is_default': False,
    },
)


def _system_spec_for_theme(theme):
    for spec in SYSTEM_THEMES:
        if theme.name == spec['name']:
            return spec
    for spec in SYSTEM_THEMES:
        if theme.base_theme == spec['base_theme']:
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
    theme.colors = DEFAULT_THEME_COLORS[spec['base_theme']]
    theme.bootstrap_colors = {}
    theme.save(update_fields=['description', 'colors', 'bootstrap_colors', 'updated_at'])
    return True


def ensure_system_themes(theme_model, *, update_existing=False):
    """Создаёт системные темы light/dark, если их ещё нет."""
    created = []
    updated = []

    for spec in SYSTEM_THEMES:
        defaults = {
            'description': spec['description'],
            'author': 'System',
            'base_theme': spec['base_theme'],
            'colors': DEFAULT_THEME_COLORS[spec['base_theme']],
            'bootstrap_colors': {},
            'is_active': False,
            'is_default': spec['is_default'],
        }
        lookup = {
            'name': spec['name'],
            'is_system': True,
        }
        if _model_has_field(theme_model, 'module_key'):
            lookup['module_key'] = None
        theme, was_created = theme_model.objects.get_or_create(
            **lookup,
            defaults=defaults,
        )
        if was_created:
            created.append(theme)
            continue
        if not update_existing:
            continue
        reset_system_theme_to_defaults(theme)
        updated.append(theme)

    return created, updated


AI_ASSISTANT_THEME_COLORS = {
    'headerBackground': 'rgba(10, 12, 18, 0.92)',
    'authBackground': 'rgba(5, 5, 8, 0.95)',
    'background': '#050508',
    'border': 'rgba(58, 232, 255, 0.12)',
    'primaryText': '#e8ecf4',
    'secondaryText': '#a0aec0',
    'primaryBackground': '#0e1118',
    'secondaryBackground': '#13161f',
    'hoverBackground': '#191d28',
    'accent': '#3ae8ff',
}

AI_ASSISTANT_MODULE_TOKENS = {
    'neonCyan': '#3ae8ff',
    'neonPurple': '#a855f7',
    'neonGreen': '#22ff8d',
    'neonPink': '#ff6eb4',
    'neonBlue': '#4f8fff',
    'glowCyan': '0 0 20px rgba(58, 232, 255, 0.4), 0 0 40px rgba(58, 232, 255, 0.2)',
}

AI_ASSISTANT_LIGHT_COLORS = {
    'headerBackground': 'rgba(248, 250, 252, 0.92)',
    'authBackground': 'rgba(248, 250, 252, 0.95)',
    'background': '#f8fafc',
    'border': 'rgba(15, 118, 138, 0.15)',
    'primaryText': '#0f172a',
    'secondaryText': '#334155',
    'primaryBackground': '#f1f5f9',
    'secondaryBackground': '#e2e8f0',
    'hoverBackground': '#cbd5e1',
    'accent': '#0e7490',
}

BUILTIN_MODULE_MANIFESTS = (
    {
        'moduleKey': 'ai_assistant',
        'displayName': 'AI-ассистент',
        'modulePair': 'default',
        'baseTheme': 'dark',
        'colors': AI_ASSISTANT_THEME_COLORS,
        'bootstrap_colors': {},
        'moduleTokens': AI_ASSISTANT_MODULE_TOKENS,
        'systemThemes': (
            {
                'name': 'Neural (AI-ассистент)',
                'description': 'Системная пара тем AI-ассистента',
                'base_theme': 'dark',
                'module_pair': 'default',
                'is_default': True,
            },
            {
                'name': 'Neural (AI-ассистент)',
                'description': 'Системная пара тем AI-ассистента',
                'base_theme': 'light',
                'module_pair': 'default',
                'is_default': True,
                'colors': AI_ASSISTANT_LIGHT_COLORS,
            },
        ),
    },
)


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


def ensure_module_themes_from_manifests(theme_model, manifests, *, update_existing=False):
    """Создаёт/обновляет системные темы модулей из manifest (клиент или builtin)."""
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
            defaults = {
                'description': spec.get('description', ''),
                'author': 'System',
                'base_theme': spec['base_theme'],
                'module_key': manifest['module_key'],
                'module_pair': spec.get('module_pair') or manifest.get('module_pair') or 'default',
                'colors': colors,
                'bootstrap_colors': manifest['bootstrap_colors'],
                'module_tokens': module_tokens,
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
            theme.save(
                update_fields=[
                    'description', 'colors', 'bootstrap_colors',
                    'module_tokens', 'base_theme', 'module_pair', 'name', 'updated_at',
                ]
            )
            updated.append(theme)

    return created, updated


def ensure_builtin_module_themes(theme_model, *, update_existing=False):
    return ensure_module_themes_from_manifests(
        theme_model,
        BUILTIN_MODULE_MANIFESTS,
        update_existing=update_existing,
    )
