"""Переименование Индиго, Циан и Служебный и сброс цветов этих пар и «Высокого контраста»."""

from django.db import migrations

from src.core.settings.services.theme_seed import (
    SYSTEM_THEME_RENAME_MAP,
    SYSTEM_THEMES,
    rename_system_themes,
    reset_system_theme_to_defaults,
)

# Только эти системные темы сайта получают новые цвета.
# is_active и is_default reset_system_theme_to_defaults не трогает.
RECOLOR_THEME_NAMES = (
    'Слива',
    'Слива · тёмная',
    'Олива',
    'Олива · тёмная',
    'Бордо',
    'Бордо · тёмная',
    'Высокий контраст',
    'Высокий контраст · тёмная',
)


def recolor_named_system_themes(apps, schema_editor):
    Theme = apps.get_model('settings', 'Theme')
    descriptions = {spec['name']: spec['description'] for spec in SYSTEM_THEMES}
    rename_system_themes(Theme, SYSTEM_THEME_RENAME_MAP, descriptions=descriptions)
    themes = Theme.objects.filter(
        is_system=True,
        module_key__isnull=True,
        name__in=RECOLOR_THEME_NAMES,
    )
    for theme in themes:
        reset_system_theme_to_defaults(theme)


def noop_reverse(apps, schema_editor):
    pass


class Migration(migrations.Migration):

    dependencies = [
        ('settings', '0039_theme_theme_pair'),
    ]

    operations = [
        migrations.RunPython(recolor_named_system_themes, noop_reverse),
    ]
