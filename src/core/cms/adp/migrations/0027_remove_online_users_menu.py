from django.db import migrations


def remove_online_users_menu(apps, schema_editor):
    MenuItem = apps.get_model('cms_adp', 'MenuItem')
    MenuItem.objects.filter(route_name='OnlineUsersPanel').delete()


class Migration(migrations.Migration):

    dependencies = [
        ('cms_adp', '0026_restore_admin_panel_menu_children'),
    ]

    operations = [
        migrations.RunPython(remove_online_users_menu, migrations.RunPython.noop),
    ]
