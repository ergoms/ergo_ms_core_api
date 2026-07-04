# -*- coding: utf-8 -*-
"""Объединяет пункты меню «Политики и права» и «Ограничения» в «Доступ и права»."""

from django.db import migrations

NEW_ROUTE_NAME = 'AccessControlPanel'
OLD_ROUTE_NAMES = (
    'PermissionsPanel',
    'LiminationPanel',
    'ModulePagePermissionsPanel',
)


def consolidate_access_menu(apps, schema_editor):
    MenuItem = apps.get_model('cms_adp', 'MenuItem')

    permissions_item = MenuItem.objects.filter(route_name='PermissionsPanel').first()
    limitations_item = MenuItem.objects.filter(route_name='LiminationPanel').first()

    preserved_order = None
    preserved_parent = None

    if permissions_item is not None:
        preserved_order = permissions_item.order
        preserved_parent = permissions_item.parent
        permissions_item.name = 'Доступ и права'
        permissions_item.route_name = NEW_ROUTE_NAME
        permissions_item.save(update_fields=['name', 'route_name'])
    elif limitations_item is not None:
        preserved_order = limitations_item.order
        preserved_parent = limitations_item.parent
        limitations_item.name = 'Доступ и права'
        limitations_item.route_name = NEW_ROUTE_NAME
        limitations_item.save(update_fields=['name', 'route_name'])

    MenuItem.objects.filter(
        route_name__in=['LiminationPanel', 'ModulePagePermissionsPanel'],
    ).delete()

    admin_panel = MenuItem.objects.filter(route_name='AdminPanel').first()
    parent = preserved_parent or admin_panel

    if parent is not None and not MenuItem.objects.filter(route_name=NEW_ROUTE_NAME).exists():
        from django.db.models import Max

        max_order = MenuItem.objects.filter(parent=parent).aggregate(
            Max('order'),
        )['order__max'] or 0

        MenuItem.objects.create(
            name='Доступ и права',
            route_name=NEW_ROUTE_NAME,
            icon='Shield',
            item_type='route',
            parent=parent,
            order=preserved_order if preserved_order is not None else max_order + 10,
            is_active=True,
            is_admin_only=True,
            module_source='core/cms',
        )


def restore_access_menu(apps, schema_editor):
    MenuItem = apps.get_model('cms_adp', 'MenuItem')

    access_item = MenuItem.objects.filter(route_name=NEW_ROUTE_NAME).first()
    if access_item is None:
        return

    access_item.name = 'Политики и права'
    access_item.route_name = 'PermissionsPanel'
    access_item.save(update_fields=['name', 'route_name'])

    admin_panel = access_item.parent
    if admin_panel is None:
        return

    if not MenuItem.objects.filter(route_name='LiminationPanel').exists():
        MenuItem.objects.create(
            name='Ограничения',
            route_name='LiminationPanel',
            icon='Lock',
            item_type='route',
            parent=admin_panel,
            order=access_item.order + 10,
            is_active=True,
            is_admin_only=True,
            module_source='core/cms',
        )


class Migration(migrations.Migration):

    dependencies = [
        ('cms_adp', '0036_add_audit_log_menu'),
    ]

    operations = [
        migrations.RunPython(consolidate_access_menu, restore_access_menu),
    ]
