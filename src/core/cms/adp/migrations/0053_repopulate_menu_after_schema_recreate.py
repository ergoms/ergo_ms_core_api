# -*- coding: utf-8 -*-
"""
После 0051 (DeleteModel MenuItem) и 0052 (CreateModel без данных) меню пустое.
Восстанавливаем дерево через restore_menu, если ядро ещё не засеяно.
"""

from django.core.management import call_command
from django.db import migrations

# Не включать в _discover_core_menu_migrations (иначе restore_menu вызовет сам себя).
MENU_RESTORE_ORCHESTRATOR = True


def restore_menu_if_core_missing(apps, schema_editor):
    MenuItem = apps.get_model('cms_adp', 'MenuItem')
    if MenuItem.objects.filter(module_source='core/cms').exists():
        return
    call_command('restore_menu')


class Migration(migrations.Migration):

    dependencies = [
        ('cms_adp', '0052_restore_menu_models'),
    ]

    operations = [
        migrations.RunPython(
            restore_menu_if_core_missing,
            migrations.RunPython.noop,
        ),
    ]
