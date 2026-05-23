from django.db import migrations


def remove_security_settings_menu(apps, schema_editor):
    """Удаляет пункт меню SecuritySettings, если он есть. Идемпотентно."""
    MenuItem = apps.get_model('cms_adp', 'MenuItem')
    MenuItem.objects.filter(route_name='SecuritySettings').delete()


class Migration(migrations.Migration):

    dependencies = [
        ('cms_adp', '0016_alter_menuitem_item_type'),
    ]

    operations = [
        migrations.RunPython(remove_security_settings_menu, migrations.RunPython.noop),
    ]
