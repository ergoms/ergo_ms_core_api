# -*- coding: utf-8 -*-

from django.db import migrations


def add_theme_editor_menu(apps, schema_editor):
    from src.core.cms.adp.menu.migration_utils import MenuMigrationHelper

    MenuItem = apps.get_model('cms_adp', 'MenuItem')
    if MenuItem.objects.filter(route_name='ThemeEditor').exists():
        return

    settings_menu = MenuItem.objects.filter(route_name='Settings').first()
    if not settings_menu:
        return

    cms = MenuMigrationHelper(apps, 'core/cms')
    cms.create_route(
        'Темы оформления',
        'ThemeEditor',
        parent=settings_menu,
        icon='Palette',
        order=10,
        is_admin_only=True,
    )


def remove_theme_editor_menu(apps, schema_editor):
    MenuItem = apps.get_model('cms_adp', 'MenuItem')
    MenuItem.objects.filter(route_name='ThemeEditor').delete()


class Migration(migrations.Migration):

    dependencies = [
        ('cms_adp', '0022_remove_legacy_site_content_menu'),
    ]

    operations = [
        migrations.RunPython(add_theme_editor_menu, remove_theme_editor_menu),
    ]
