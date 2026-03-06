# -*- coding: utf-8 -*-
"""
Удаляет пункты меню модуля bi_analysis из core-миграций.
Модуль bi_analysis заменён на bi_analysis_modern; меню управляется
миграциями самого модуля при его установке.
"""

from django.db import migrations


def remove_bi_analysis_menu(apps, schema_editor):
    MenuItem = apps.get_model('cms_adp', 'MenuItem')
    MenuItem.objects.filter(module_source='modules/bi_analysis').delete()


class Migration(migrations.Migration):

    dependencies = [
        ('cms_adp', '0013_bi_module_source_to_modules_bi_analysis'),
    ]

    operations = [
        migrations.RunPython(remove_bi_analysis_menu, migrations.RunPython.noop),
    ]
