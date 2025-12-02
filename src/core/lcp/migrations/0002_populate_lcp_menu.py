# -*- coding: utf-8 -*-
"""
Миграция данных: заполнение меню для модуля LCP (Low-Code Platform).
"""

from django.db import migrations


def populate_lcp_menu(apps, schema_editor):
    """Создаёт элементы меню для LCP модуля."""
    from src.core.cms.adp.menu.migration_utils import MenuMigrationHelper
    
    # === LCP ===
    lcp = MenuMigrationHelper(apps, 'core/lcp')
    lcp.clear_module_items()
    
    # Группа LCP (фиксированный order=40)
    lcp_menu = lcp.create_group('Low-Code Platform', 'lcp-home', icon='Code', order=40)
    lcp.create_routes_batch([
        ('Главная', 'lcp-home', 'Home'),
        ('Модули', 'lcp-modules', 'Folder'),
    ], parent=lcp_menu)


def reverse_populate_lcp_menu(apps, schema_editor):
    """Удаляет элементы меню LCP модуля."""
    MenuItem = apps.get_model('cms_adp', 'MenuItem')
    MenuItem.objects.filter(module_source='core/lcp').delete()


class Migration(migrations.Migration):
    
    dependencies = [
        ('lcp', '0001_initial'),
        ('cms_adp', '0008_alter_menuitem_order'),
    ]
    
    operations = [
        migrations.RunPython(
            populate_lcp_menu,
            reverse_populate_lcp_menu
        ),
    ]

