# -*- coding: utf-8 -*-

from django.db import migrations


def rename_site_settings_menu_to_system(apps, schema_editor):
    MenuItem = apps.get_model('cms_adp', 'MenuItem')
    MenuItem.objects.filter(route_name='Settings', name='Настройки сайта').update(
        name='Настройки системы',
    )


def reverse_rename_site_settings_menu_to_system(apps, schema_editor):
    MenuItem = apps.get_model('cms_adp', 'MenuItem')
    MenuItem.objects.filter(route_name='Settings', name='Настройки системы').update(
        name='Настройки сайта',
    )


class Migration(migrations.Migration):

    dependencies = [
        ('cms_adp', '0027_remove_online_users_menu'),
    ]

    operations = [
        migrations.RunPython(
            rename_site_settings_menu_to_system,
            reverse_rename_site_settings_menu_to_system,
        ),
    ]
