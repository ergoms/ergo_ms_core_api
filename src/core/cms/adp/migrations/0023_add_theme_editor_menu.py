# -*- coding: utf-8 -*-

from django.db import migrations


def add_theme_editor_menu(apps, schema_editor):
    from src.core.cms.adp.menu.migration_utils import MenuMigrationHelper

    MenuItem = apps.get_model('cms_adp', 'MenuItem')
    if MenuItem.objects.filter(route_name='ThemeEditor').exists():
        return

    cms = MenuMigrationHelper(apps, 'core/cms')
    admin_panel = MenuItem.objects.filter(route_name='AdminPanel').first()
    if not admin_panel:
        return

    cms.create_route('Темы оформления', 'ThemeEditor', parent=admin_panel, icon='Palette')


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
