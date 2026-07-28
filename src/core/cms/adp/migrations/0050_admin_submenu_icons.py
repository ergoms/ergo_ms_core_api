# -*- coding: utf-8 -*-
"""Задаёт Lucide-иконки у вложенных пунктов админ-панели (вместо Dot в sidebar)."""

from django.db import migrations

ICON_BY_ROUTE = {
    'CategoriesPanel': 'BadgeCheck',
    'GroupsPanel': 'UsersRound',
    'AccessControlPanel': 'Shield',
    'MenuPanel': 'PanelLeft',
}


def set_admin_submenu_icons(apps, schema_editor):
    MenuItem = apps.get_model('cms_adp', 'MenuItem')
    for route_name, icon in ICON_BY_ROUTE.items():
        MenuItem.objects.filter(route_name=route_name).update(icon=icon)


def clear_admin_submenu_icons(apps, schema_editor):
    MenuItem = apps.get_model('cms_adp', 'MenuItem')
    MenuItem.objects.filter(route_name__in=ICON_BY_ROUTE.keys()).update(icon=None)


class Migration(migrations.Migration):

    dependencies = [
        ('cms_adp', '0049_alter_menuitem_module_source'),
    ]

    operations = [
        migrations.RunPython(set_admin_submenu_icons, clear_admin_submenu_icons),
    ]
