# -*- coding: utf-8 -*-
"""
Миграция данных: обновление module_source для пунктов меню BI
с 'core/bi' на 'modules/bi_analysis' после переноса модуля в modules/bi_analysis.
"""

from django.db import migrations


def update_bi_module_source(apps, schema_editor):
    MenuItem = apps.get_model('cms_adp', 'MenuItem')
    MenuItem.objects.filter(module_source='core/bi').update(module_source='modules/bi_analysis')


def reverse_bi_module_source(apps, schema_editor):
    MenuItem = apps.get_model('cms_adp', 'MenuItem')
    MenuItem.objects.filter(module_source='modules/bi_analysis').update(module_source='core/bi')


class Migration(migrations.Migration):

    dependencies = [
        ('cms_adp', '0012_shortcodes_module_source_to_cms_shortcodes'),
    ]

    operations = [
        migrations.RunPython(update_bi_module_source, reverse_bi_module_source),
    ]
