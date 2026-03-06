# -*- coding: utf-8 -*-
"""
Миграция данных: обновление module_source для пунктов меню шорткодов
с 'core/shortcodes' на 'cms_shortcodes' после переноса модуля в modules/cms_shortcodes.
"""

from django.db import migrations


def update_shortcodes_module_source(apps, schema_editor):
    MenuItem = apps.get_model('cms_adp', 'MenuItem')
    MenuItem.objects.filter(module_source='core/shortcodes').update(module_source='cms_shortcodes')


def reverse_shortcodes_module_source(apps, schema_editor):
    MenuItem = apps.get_model('cms_adp', 'MenuItem')
    MenuItem.objects.filter(module_source='cms_shortcodes').update(module_source='core/shortcodes')


class Migration(migrations.Migration):

    dependencies = [
        ('cms_adp', '0011_remove_neural_networks_hub_menu'),
    ]

    operations = [
        migrations.RunPython(update_shortcodes_module_source, reverse_shortcodes_module_source),
    ]
