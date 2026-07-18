from django.db import migrations

from src.core.settings.services.theme_seed import (
    ACCESSIBILITY_THEME_RENAME_MAP,
    SYSTEM_THEMES,
    ensure_system_themes,
    rename_system_themes,
)


def rename_accessibility_theme_names(apps, schema_editor):
    Theme = apps.get_model('settings', 'Theme')
    name_to_description = {spec['name']: spec['description'] for spec in SYSTEM_THEMES}
    rename_system_themes(
        Theme,
        ACCESSIBILITY_THEME_RENAME_MAP,
        descriptions=name_to_description,
    )
    ensure_system_themes(Theme)


class Migration(migrations.Migration):

    dependencies = [
        ('settings', '0030_seed_accessibility_system_themes'),
    ]

    operations = [
        migrations.RunPython(rename_accessibility_theme_names, migrations.RunPython.noop),
    ]
