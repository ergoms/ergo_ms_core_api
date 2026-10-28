"""Мягкий контур блоков у Бирюзы, Оливы, Сливы, Бордо и Небесного."""

from django.db import migrations

from src.core.settings.services.theme_seed import SYSTEM_THEMES

BORDER_THEME_NAMES = (
    'Бирюза',
    'Бирюза · тёмная',
    'Олива',
    'Олива · тёмная',
    'Слива',
    'Слива · тёмная',
    'Бордо',
    'Бордо · тёмная',
    'Небесный',
    'Небесный · тёмная',
)


def soften_named_theme_borders(apps, schema_editor):
    Theme = apps.get_model('settings', 'Theme')
    borders = {
        spec['name']: spec['colors']['border']
        for spec in SYSTEM_THEMES
        if spec['name'] in BORDER_THEME_NAMES
    }
    themes = Theme.objects.filter(
        is_system=True,
        module_key__isnull=True,
        name__in=BORDER_THEME_NAMES,
    )
    for theme in themes:
        colors = dict(theme.colors or {})
        colors['border'] = borders[theme.name]
        theme.colors = colors
        theme.save(update_fields=['colors', 'updated_at'])


def noop_reverse(apps, schema_editor):
    pass


class Migration(migrations.Migration):

    dependencies = [
        ('settings', '0040_recolor_named_system_themes'),
    ]

    operations = [
        migrations.RunPython(soften_named_theme_borders, noop_reverse),
    ]
