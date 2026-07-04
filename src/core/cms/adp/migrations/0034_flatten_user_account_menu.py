# -*- coding: utf-8 -*-

from django.db import migrations


def flatten_user_account_menu(apps, schema_editor):
    MenuItem = apps.get_model('cms_adp', 'MenuItem')

    user_menu = MenuItem.objects.filter(
        module_source='core/cms',
        name='Личный кабинет',
    ).first()
    if user_menu is None:
        return

    MenuItem.objects.filter(parent=user_menu, route_name='Account').delete()

    user_menu.route_name = 'Account'
    user_menu.save(update_fields=['route_name'])


def restore_user_account_menu(apps, schema_editor):
    from src.core.cms.adp.menu.migration_utils import MenuMigrationHelper

    MenuItem = apps.get_model('cms_adp', 'MenuItem')
    user_menu = MenuItem.objects.filter(
        module_source='core/cms',
        name='Личный кабинет',
    ).first()
    if user_menu is None:
        return

    user_menu.route_name = 'User'
    user_menu.save(update_fields=['route_name'])

    cms = MenuMigrationHelper(apps, 'core/cms')
    cms.create_route('Профиль', 'Account', parent=user_menu)


class Migration(migrations.Migration):

    dependencies = [
        ('cms_adp', '0033_remove_userprofile_location_fields'),
    ]

    operations = [
        migrations.RunPython(flatten_user_account_menu, restore_user_account_menu),
    ]
