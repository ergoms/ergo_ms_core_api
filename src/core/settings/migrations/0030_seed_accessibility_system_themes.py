from django.db import migrations

from src.core.settings.services.theme_seed import ensure_system_themes


def seed_accessibility_system_themes(apps, schema_editor):
    Theme = apps.get_model('settings', 'Theme')
    ensure_system_themes(Theme)


class Migration(migrations.Migration):

    dependencies = [
        ('settings', '0029_rename_and_seed_system_themes'),
    ]

    operations = [
        migrations.RunPython(seed_accessibility_system_themes, migrations.RunPython.noop),
    ]
