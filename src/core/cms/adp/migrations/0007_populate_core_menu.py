# -*- coding: utf-8 -*-
"""
Миграция данных: заполнение базового меню из core модулей.
Включает элементы из: cms, ai-assistant.

Порядок элементов определяется последовательностью создания.
"""

from django.db import migrations


def populate_core_menu(apps, schema_editor):
    """Создаёт базовые элементы меню из core модулей."""
    from src.core.cms.adp.menu.migration_utils import MenuMigrationHelper
    
    # === CMS ===
    cms = MenuMigrationHelper(apps, 'core/cms')
    cms.clear_module_items()
    
    # Разделители
    cms.create_separator('Настройки', before_order=0)
    cms.create_separator('Модули', before_order=20)
    
    # Личный кабинет (фиксированный order=0)
    user_menu = cms.create_group('Личный кабинет', 'User', icon='CircleUserRound', order=0)
    cms.create_routes_batch([
        ('Профиль', 'Account'),
    ], parent=user_menu)
    
    # Настройки сайта (фиксированный order=10)
    settings_menu = cms.create_group('Настройки сайта', 'Settings', icon='UserCog', order=10)
    
    # Админ-панель (вложенная группа)
    admin_panel = cms.create_group(
        'Админ-панель', 'AdminPanel', 
        icon='KeySquare', 
        parent=settings_menu, 
        is_admin_only=True
    )
    users_menu = cms.create_group(
        'Пользователи', 'UsersPanel',
        icon='Users',
        parent=admin_panel,
        order=10,
    )
    cms.create_routes_batch([
        ('Все', 'UsersPanel'),
        ('В сети', 'OnlineUsersPanel'),
    ], parent=users_menu)
    cms.create_routes_batch([
        ('Роли', 'CategoriesPanel'),
        ('Ролевые группы', 'GroupsPanel'),
        ('Политики и права', 'PermissionsPanel'),
        ('Ограничения', 'LiminationPanel'),
        ('Управление меню', 'MenuPanel'),
        ('Темы оформления', 'ThemeEditor'),
    ], parent=admin_panel)
    
    # Остальные настройки — удалены: общие настройки, редактор страниц, категории страниц

def reverse_populate_core_menu(apps, schema_editor):
    """Удаляет элементы меню из core модулей."""
    MenuItem = apps.get_model('cms_adp', 'MenuItem')
    MenuSeparator = apps.get_model('cms_adp', 'MenuSeparator')
    
    MenuItem.objects.filter(module_source__startswith='core/').delete()
    MenuSeparator.objects.all().delete()


class Migration(migrations.Migration):
    
    dependencies = [
        ('cms_adp', '0006_menuseparator_menuitem_menuaccesslog'),
    ]
    
    operations = [
        migrations.RunPython(
            populate_core_menu,
            reverse_populate_core_menu
        ),
    ]
