# -*- coding: utf-8 -*-

from django.db import migrations


def remove_users_all_submenu(apps, schema_editor):
    MenuItem = apps.get_model('cms_adp', 'MenuItem')
    MenuItem.objects.filter(route_name='UsersPanel', name='Все').delete()


class Migration(migrations.Migration):

    dependencies = [
        ('cms_adp', '0031_rename_cms_adp_use_user_id_status_idx_cms_adp_use_user_id_a313df_idx'),
    ]

    operations = [
        migrations.RunPython(remove_users_all_submenu, migrations.RunPython.noop),
    ]
