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
        theme, was_created = theme_model.objects.get_or_create(
            name=spec['name'],
            is_system=True,
            defaults=defaults,
        )
        if was_created:
            created.append(theme)
            continue
        if not update_existing:
            continue
        theme.colors = DEFAULT_THEME_COLORS[spec['base_theme']]
        theme.bootstrap_colors = {}
        theme.save(update_fields=['colors', 'bootstrap_colors', 'updated_at'])
        updated.append(theme)

    return created, updated
