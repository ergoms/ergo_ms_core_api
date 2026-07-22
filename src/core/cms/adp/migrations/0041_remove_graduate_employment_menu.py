# -*- coding: utf-8 -*-
"""Удаление меню и прав модуля graduate_employment."""

from django.db import migrations

MODULE_SOURCE = 'modules/graduate_employment'
MODULE_NAME = 'graduate_employment'


def remove_graduate_employment(apps, schema_editor):
    MenuItem = apps.get_model('cms_adp', 'MenuItem')
    ModulePermission = apps.get_model('cms_adp', 'ModulePermission')
    MenuItem.objects.filter(module_source=MODULE_SOURCE).delete()
    ModulePermission.objects.filter(module_name=MODULE_NAME).delete()


class Migration(migrations.Migration):

    dependencies = [
        ('cms_adp', '0040_migrate_user_content_type'),
    ]

    operations = [
        migrations.RunPython(remove_graduate_employment, migrations.RunPython.noop),
    ]
