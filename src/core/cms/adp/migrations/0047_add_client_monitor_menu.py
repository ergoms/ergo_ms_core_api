# -*- coding: utf-8 -*-
"""Добавляет пункт «Мониторинг клиентов» в админ-панель."""

from django.db import migrations

ROUTE_NAME = 'ClientMonitorPanel'
MODULE_SOURCE = 'core/cms'


def add_client_monitor_menu(apps, schema_editor):
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
        name='Мониторинг клиентов',
        route_name=ROUTE_NAME,
        icon='Activity',
        item_type='route',
        parent=admin_panel,
        order=max_order + 10,
        is_active=True,
        is_admin_only=True,
        module_source=MODULE_SOURCE,
    )


def remove_client_monitor_menu(apps, schema_editor):
    MenuItem = apps.get_model('cms_adp', 'MenuItem')
    MenuItem.objects.filter(route_name=ROUTE_NAME).delete()


class Migration(migrations.Migration):

    dependencies = [
        ('cms_adp', '0046_alter_userprofile_language'),
    ]

    operations = [
        migrations.RunPython(add_client_monitor_menu, remove_client_monitor_menu),
    ]
