# Generated migration data for ai_assistant module themes
from django.db import migrations


def seed_ai_assistant_themes(apps, schema_editor):
    Theme = apps.get_model('settings', 'Theme')
    from src.core.settings.services.theme_seed import ensure_builtin_module_themes
    ensure_builtin_module_themes(Theme, update_existing=True)


class Migration(migrations.Migration):

    dependencies = [
        ('settings', '0025_theme_module_pair'),
    ]

    operations = [
        migrations.RunPython(seed_ai_assistant_themes, migrations.RunPython.noop),
    ]
