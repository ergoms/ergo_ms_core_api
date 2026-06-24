# -*- coding: utf-8 -*-

from django.db import migrations


def set_site_settings_menu_admin_only(apps, schema_editor):
    MenuItem = apps.get_model('cms_adp', 'MenuItem')

    settings_root = MenuItem.objects.filter(route_name='Settings').first()
    if not settings_root:
        return

    ids_to_update = {settings_root.id}
    to_process = [settings_root.id]

    while to_process:
        child_ids = list(
            MenuItem.objects.filter(parent_id__in=to_process).values_list('id', flat=True)
        )
        ids_to_update.update(child_ids)
        to_process = child_ids

    MenuItem.objects.filter(id__in=ids_to_update).update(is_admin_only=True)


def reverse_site_settings_menu_admin_only(apps, schema_editor):
    MenuItem = apps.get_model('cms_adp', 'MenuItem')

    settings_root = MenuItem.objects.filter(route_name='Settings').first()
    if not settings_root:
        return

    ids_to_update = {settings_root.id}
    to_process = [settings_root.id]

    while to_process:
        child_ids = list(
            MenuItem.objects.filter(parent_id__in=to_process).values_list('id', flat=True)
        )
        ids_to_update.update(child_ids)
        to_process = child_ids

    MenuItem.objects.filter(id__in=ids_to_update).update(is_admin_only=False)


class Migration(migrations.Migration):

    dependencies = [
        ('cms_adp', '0018_registrationinvitation'),
    ]

    operations = [
        migrations.RunPython(
            set_site_settings_menu_admin_only,
            reverse_site_settings_menu_admin_only,
        ),
    ]
