# -*- coding: utf-8 -*-
"""Добавляет пункт «Журнал действий» в админ-панель."""

from django.db import migrations

ROUTE_NAME = 'AuditLogPanel'
MODULE_SOURCE = 'core/cms'


def add_audit_menu(apps, schema_editor):
    MenuItem = apps.get_model('cms_adp', 'MenuItem')

    admin_panel = MenuItem.objects.filter(route_name='AdminPanel').first()
    if admin_panel is None:
        return

    if MenuItem.objects.filter(route_name=ROUTE_NAME).exists():
        return

    from django.db.models import Max
    max_order = MenuItem.objects.filter(parent=admin_panel).aggregate(
        Max('order')
    )['order__max'] or 0

    MenuItem.objects.create(
        name='Журнал действий',
        route_name=ROUTE_NAME,
        icon='ScrollText',
        item_type='route',
        parent=admin_panel,
        order=max_order + 10,
        is_active=True,
        is_admin_only=True,
        module_source=MODULE_SOURCE,
    )


def remove_audit_menu(apps, schema_editor):
    MenuItem = apps.get_model('cms_adp', 'MenuItem')
    MenuItem.objects.filter(route_name=ROUTE_NAME).delete()


class Migration(migrations.Migration):

    dependencies = [
        ('cms_adp', '0035_userprofilechangerequest_phone'),
    ]

    operations = [
        migrations.RunPython(add_audit_menu, remove_audit_menu),
    ]
