# -*- coding: utf-8 -*-

from django.db import migrations


def move_theme_editor_under_settings(apps, schema_editor):
    MenuItem = apps.get_model('cms_adp', 'MenuItem')

    settings_item = MenuItem.objects.filter(route_name='Settings').first()
    theme_item = MenuItem.objects.filter(route_name='ThemeEditor').first()
    if not settings_item or not theme_item:
        return

    theme_item.parent = settings_item
    theme_item.order = 10
    theme_item.is_admin_only = True
    if not theme_item.icon:
        theme_item.icon = 'Palette'
    theme_item.save()


def restore_theme_editor_top_level(apps, schema_editor):
    MenuItem = apps.get_model('cms_adp', 'MenuItem')

    theme_item = MenuItem.objects.filter(route_name='ThemeEditor').first()
    if not theme_item:
        return

    theme_item.parent = None
    theme_item.order = 11
    theme_item.save()


class Migration(migrations.Migration):

    dependencies = [
        ('cms_adp', '0023_add_theme_editor_menu'),
    ]

    operations = [
        migrations.RunPython(
            move_theme_editor_under_settings,
            restore_theme_editor_top_level,
        ),
    ]
