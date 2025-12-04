# -*- coding: utf-8 -*-
"""
Миграция данных: добавление меню для редактора тем.
"""

from django.db import migrations


def add_theme_editor_menu(apps, schema_editor):
    """Добавляет элементы меню для редактора тем."""
    from src.core.cms.adp.menu.migration_utils import MenuMigrationHelper
    
    # Получаем модель MenuItem
    MenuItem = apps.get_model('cms_adp', 'MenuItem')
    
    # Находим родительский элемент "Настройки сайта"
    settings_menu = MenuItem.objects.filter(
        route_name='Settings',
        module_source='core/cms'
    ).first()
    
    if not settings_menu:
        return
    
    # Создаем хелпер для редактора тем
    theme_editor = MenuMigrationHelper(apps, 'core/cms')
    
    # Создаем группу "Темы оформления"
    theme_settings = theme_editor.create_group(
        'Темы оформления', 'ThemeSettings', 
        icon='Palette', 
        parent=settings_menu
    )
    
    # Создаем дочерний элемент "Редактор тем"
    theme_editor.create_route(
        'Редактор тем', 'ThemeEditor',
        parent=theme_settings,
        icon='Palette'
    )


def remove_theme_editor_menu(apps, schema_editor):
    """Удаляет элементы меню для редактора тем."""
    MenuItem = apps.get_model('cms_adp', 'MenuItem')
    
    # Удаляем элементы меню редактора тем
    MenuItem.objects.filter(
        route_name__in=['ThemeSettings', 'ThemeEditor'],
        module_source='core/cms'
    ).delete()


class Migration(migrations.Migration):
    
    dependencies = [
        ('cms_adp', '0008_alter_menuitem_order'),
    ]
    
    operations = [
        migrations.RunPython(
            add_theme_editor_menu,
            remove_theme_editor_menu
        ),
    ]

