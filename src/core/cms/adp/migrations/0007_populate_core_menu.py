# -*- coding: utf-8 -*-
"""
Миграция данных: заполнение базового меню из core модулей.
Включает элементы из: cms, bi, ai-assistant, shortcodes, categories.

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
        ('Безопасность', 'SecuritySettings'),
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
    cms.create_routes_batch([
        ('Пользователи', 'UsersPanel'),
        ('Роли', 'CategoriesPanel'),
        ('Ролевые группы', 'GroupsPanel'),
        ('Политики и права', 'PermissionsPanel'),
        ('Ограничения', 'LiminationPanel'),
        ('Управление меню', 'MenuPanel'),
    ], parent=admin_panel)
    
    # Остальные настройки
    cms.create_routes_batch([
        ('Общие настройки', 'SiteSettings'),
        ('Управление файлами', 'FileManager'),
    ], parent=settings_menu)
    
    # === Shortcodes: Редактор страниц (внутри Настройки сайта) ===
    shortcodes = MenuMigrationHelper(apps, 'core/shortcodes')
    shortcodes.clear_module_items()
    
    pages_editor = shortcodes.create_group(
        'Редактор страниц', 'Shortcodes', 
        icon='Braces', 
        parent=settings_menu
    )
    shortcodes.create_routes_batch([
        ('Главная', 'MainShortcodePage'),
        ('Компоненты', 'Templates'),
        ('Страницы', 'Pages'),
        ('Разметка сайта', 'Layouts'),
        ('Категории шорткодов', 'PageShortcodeCategories'),
    ], parent=pages_editor)
    
    # === Categories: Категории страниц (внутри Настройки сайта) ===
    categories = MenuMigrationHelper(apps, 'core/categories')
    categories.clear_module_items()
    
    page_categories = categories.create_group(
        'Категории страниц', 'Categories', 
        icon='Layers', 
        parent=settings_menu
    )
    categories.create_routes_batch([
        ('Категории', 'PageCategories'),
        ('Создание категорий', 'PageCategoriesManager'),
        ('Создание тегов', 'TagsManager'),
    ], parent=page_categories)
    
    # === BI (фиксированный order=20) ===
    bi = MenuMigrationHelper(apps, 'core/bi')
    bi.clear_module_items()
    
    bi_menu = bi.create_group('BI', 'BI', icon='ChartSpline', order=20)
    bi.create_offcanvas_batch([
        ('Датасеты', 'datasets', 'Database'),
        ('Подключения', 'connections', 'Plug'),
        ('Чарты', 'charts', 'BarChart3'),
        ('Дашборды', 'dashboards', 'LayoutDashboard'),
    ], parent=bi_menu)
    
    # === AI Assistant (фиксированный order=30) ===
    ai = MenuMigrationHelper(apps, 'core/ai-assistant')
    ai.clear_module_items()
    
    ai_menu = ai.create_group('AI Hub', 'AIAssistantHub', icon='Bot', order=30)
    ai.create_routes_batch([
        ('Центр управления', 'AIAssistantHub', 'Bot'),
        ('Чат', 'AIAssistantChat', 'MessageSquare'),
        ('BI Анализ', 'AIAssistantBI', 'Database'),
    ], parent=ai_menu)


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
