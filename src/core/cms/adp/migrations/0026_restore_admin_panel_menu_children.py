# -*- coding: utf-8 -*-

from django.db import migrations


def _ensure_admin_panel_children(cms, MenuItem, admin_panel):
    users_menu = MenuItem.objects.filter(route_name='UsersPanel', parent=admin_panel).first()
    if not users_menu:
        users_menu = cms.create_group(
            'Пользователи',
            'UsersPanel',
            icon='Users',
            parent=admin_panel,
            order=10,
            is_admin_only=True,
        )

    if not MenuItem.objects.filter(parent=users_menu, route_name='UsersPanel', name='Все').exists():
        cms.create_route('Все', 'UsersPanel', parent=users_menu, is_admin_only=True)
    if not MenuItem.objects.filter(parent=users_menu, route_name='OnlineUsersPanel').exists():
        cms.create_route('В сети', 'OnlineUsersPanel', parent=users_menu, is_admin_only=True)

    admin_routes = [
        ('Роли', 'CategoriesPanel'),
        ('Ролевые группы', 'GroupsPanel'),
        ('Политики и права', 'PermissionsPanel'),
        ('Ограничения', 'LiminationPanel'),
        ('Управление меню', 'MenuPanel'),
    ]
    for order, (name, route_name) in enumerate(admin_routes, start=20):
        if not MenuItem.objects.filter(parent=admin_panel, route_name=route_name).exists():
            cms.create_route(
                name,
                route_name,
                parent=admin_panel,
                order=order,
                is_admin_only=True,
            )


def restore_admin_panel_menu(apps, schema_editor):
    from src.core.cms.adp.menu.migration_utils import MenuMigrationHelper

    MenuItem = apps.get_model('cms_adp', 'MenuItem')
    settings = MenuItem.objects.filter(route_name='Settings').first()
    if not settings:
        return

    cms = MenuMigrationHelper(apps, 'core/cms')

    admin_panel = MenuItem.objects.filter(route_name='AdminPanel').first()
    if not admin_panel:
        admin_panel = cms.create_group(
            'Админ-панель',
            'AdminPanel',
            icon='KeySquare',
            parent=settings,
            order=10,
            is_admin_only=True,
        )
    else:
        admin_panel.parent = settings
        admin_panel.order = 10
        admin_panel.is_admin_only = True
        admin_panel.save()

    theme_item = MenuItem.objects.filter(route_name='ThemeEditor').first()
    if theme_item:
        theme_item.parent = settings
        theme_item.order = 20
        theme_item.name = 'Темы оформления'
        theme_item.is_admin_only = True
        theme_item.save()
        MenuItem.objects.filter(route_name='ThemeEditor').exclude(id=theme_item.id).delete()
    else:
        cms.create_route(
            'Темы оформления',
            'ThemeEditor',
            parent=settings,
            icon='Palette',
            order=20,
            is_admin_only=True,
        )

    MenuItem.objects.filter(route_name='ThemeSettings').delete()

    _ensure_admin_panel_children(cms, MenuItem, admin_panel)


class Migration(migrations.Migration):

    dependencies = [
        ('cms_adp', '0025_site_settings_two_tabs_menu'),
    ]

    operations = [
        migrations.RunPython(
            restore_admin_panel_menu,
            migrations.RunPython.noop,
        ),
    ]
