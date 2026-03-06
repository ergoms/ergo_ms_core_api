# -*- coding: utf-8 -*-
"""
Удаляет все пункты меню, не принадлежащие core/cms.

Модули, которые ранее создавали элементы меню через core-миграции или
через собственные миграции (ai_assistant, lcp, cms_shortcodes, bi_analysis,
learning_analytics, neural_networks_hub, porosity_analysis,
technical_process_analysis и др.), теперь являются сабмодулями и управляют
своим меню самостоятельно при установке.

После этой миграции в меню по умолчанию остаётся только core/cms:
  - Личный кабинет (Профиль, Безопасность)
  - Настройки сайта (Админ-панель, Общие настройки, Управление файлами,
    Темы оформления, Редактор тем)
"""

from django.db import migrations


def remove_non_core_menu_items(apps, schema_editor):
    MenuItem = apps.get_model('cms_adp', 'MenuItem')
    # Оставляем только core/cms; всё остальное (включая NULL) — удаляем
    MenuItem.objects.exclude(module_source='core/cms').delete()


class Migration(migrations.Migration):

    dependencies = [
        ('cms_adp', '0014_remove_bi_analysis_menu'),
    ]

    operations = [
        migrations.RunPython(remove_non_core_menu_items, migrations.RunPython.noop),
    ]
