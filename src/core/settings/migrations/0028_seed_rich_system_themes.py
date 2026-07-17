from django.db import migrations

from src.core.settings.services.theme_seed import ensure_system_themes


def seed_rich_system_themes(apps, schema_editor):
    Theme = apps.get_model('settings', 'Theme')
    ensure_system_themes(Theme)


class Migration(migrations.Migration):

    dependencies = [
        ('settings', '0027_seed_accent_system_themes'),
    ]

    operations = [
        migrations.RunPython(seed_rich_system_themes, migrations.RunPython.noop),
    ]
