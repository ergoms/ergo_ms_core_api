from django.db import migrations

from src.core.settings.services.theme_seed import (
    ACCESSIBILITY_THEME_RENAME_MAP,
    SYSTEM_THEMES,
    ensure_system_themes,
)


def rename_accessibility_theme_names(apps, schema_editor):
    Theme = apps.get_model('settings', 'Theme')
    name_to_description = {spec['name']: spec['description'] for spec in SYSTEM_THEMES}

    qs = Theme.objects.filter(is_system=True)
    if hasattr(Theme, 'module_key'):
        qs = qs.filter(module_key__isnull=True)

    for theme in qs:
        new_name = ACCESSIBILITY_THEME_RENAME_MAP.get(theme.name)
        if not new_name:
            continue
        theme.name = new_name
        theme.description = name_to_description.get(new_name, theme.description)
        theme.save(update_fields=['name', 'description', 'updated_at'])

    ensure_system_themes(Theme)


class Migration(migrations.Migration):

    dependencies = [
        ('settings', '0030_seed_accessibility_system_themes'),
    ]

    operations = [
        migrations.RunPython(rename_accessibility_theme_names, migrations.RunPython.noop),
    ]
