# -*- coding: utf-8 -*-
"""
После 0051/0052 таблицы меню пустые.

Раньше здесь вызывался restore_menu, но живые модели уже требуют
catalog_key (0054), а колонки ещё нет — PostgreSQL падает на SELECT.

Засев перенесён в конец 0054 (после AddField catalog_key / layout).
Эта миграция остаётся no-op, чтобы не ломать цепочку зависимостей.
"""

from django.db import migrations

# Не включать в _discover_core_menu_migrations (иначе restore_menu вызовет сам себя).
MENU_RESTORE_ORCHESTRATOR = True


class Migration(migrations.Migration):

    dependencies = [
        ('cms_adp', '0052_restore_menu_models'),
    ]

    operations = [
        migrations.RunPython(
            migrations.RunPython.noop,
            migrations.RunPython.noop,
        ),
    ]
