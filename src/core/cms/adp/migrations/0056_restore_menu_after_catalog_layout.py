# -*- coding: utf-8 -*-
"""
После 0051–0052 меню пустое; 0053 не может вызывать restore_menu до catalog_key.
0054 добавляет catalog_key/layout. Здесь — засев меню вне schema-транзакции
(иначе PostgreSQL: CREATE INDEX при отложенных trigger events после массовых INSERT).
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
    # Массовый seed + индексы в одной atomic-транзакции ломают PostgreSQL.
    atomic = False

    dependencies = [
        ('cms_adp', '0055_alter_menuitem_order_and_more'),
    ]

    operations = [
        migrations.RunPython(
            restore_menu_if_core_missing,
            migrations.RunPython.noop,
        ),
    ]
