# -*- coding: utf-8 -*-
"""Объединяет «Мониторинг клиентов» с «Журнал действий» в один пункт меню."""

from django.db import migrations

AUDIT_ROUTE = 'AuditLogPanel'
CLIENT_MONITOR_ROUTE = 'ClientMonitorPanel'


def consolidate_action_log_menu(apps, schema_editor):
    MenuItem = apps.get_model('cms_adp', 'MenuItem')

    audit_item = MenuItem.objects.filter(route_name=AUDIT_ROUTE).first()
    client_item = MenuItem.objects.filter(route_name=CLIENT_MONITOR_ROUTE).first()

    if audit_item is not None:
        if audit_item.name != 'Журнал действий':
            audit_item.name = 'Журнал действий'
            audit_item.save(update_fields=['name'])
    elif client_item is not None:
        client_item.name = 'Журнал действий'
        client_item.route_name = AUDIT_ROUTE
        client_item.icon = 'ScrollText'
        client_item.save(update_fields=['name', 'route_name', 'icon'])
    else:
        admin_panel = MenuItem.objects.filter(route_name='AdminPanel').first()
        if admin_panel is not None:
            from django.db.models import Max

            max_order = MenuItem.objects.filter(parent=admin_panel).aggregate(
                Max('order'),
            )['order__max'] or 0

            MenuItem.objects.create(
                name='Журнал действий',
                route_name=AUDIT_ROUTE,
                icon='ScrollText',
                item_type='route',
                parent=admin_panel,
                order=max_order + 10,
                is_active=True,
                is_admin_only=True,
                module_source='core/cms',
            )

    MenuItem.objects.filter(route_name=CLIENT_MONITOR_ROUTE).delete()


def restore_client_monitor_menu(apps, schema_editor):
    MenuItem = apps.get_model('cms_adp', 'MenuItem')

    if MenuItem.objects.filter(route_name=CLIENT_MONITOR_ROUTE).exists():
        return

    admin_panel = MenuItem.objects.filter(route_name='AdminPanel').first()
    if admin_panel is None:
        return

    from django.db.models import Max

    max_order = MenuItem.objects.filter(parent=admin_panel).aggregate(
        Max('order'),
    )['order__max'] or 0

    MenuItem.objects.create(
        name='Мониторинг клиентов',
        route_name=CLIENT_MONITOR_ROUTE,
        icon='Activity',
        item_type='route',
        parent=admin_panel,
        order=max_order + 10,
        is_active=True,
        is_admin_only=True,
        module_source='core/cms',
    )


class Migration(migrations.Migration):

    dependencies = [
        ('cms_adp', '0047_add_client_monitor_menu'),
    ]

    operations = [
        migrations.RunPython(consolidate_action_log_menu, restore_client_monitor_menu),
    ]
