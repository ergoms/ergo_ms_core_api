# Generated migration data for ai_assistant module themes
from django.db import migrations


def seed_ai_assistant_themes(apps, schema_editor):
    # Ранее вызывал ensure_builtin_module_themes (no-op). Модульные темы —
    # через POST settings/themes/sync-module-defaults / ensure_module_themes_from_manifests.
    pass


class Migration(migrations.Migration):

    dependencies = [
        ('settings', '0025_theme_module_pair'),
    ]

    operations = [
        migrations.RunPython(seed_ai_assistant_themes, migrations.RunPython.noop),
    ]
