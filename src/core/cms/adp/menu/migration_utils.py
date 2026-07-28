# -*- coding: utf-8 -*-
"""
Утилиты для миграций меню.

Использование в миграциях:
    from src.core.cms.adp.menu.migration_utils import MenuMigrationHelper

    def populate_menu(apps, schema_editor):
        helper = MenuMigrationHelper(apps, 'modules/<name>')

        # Корневой элемент (order вычисляется автоматически)
        root = helper.create_group('Мой модуль', 'MyModule', icon='Folder')

        # Дочерние элементы (порядок = порядок создания)
        helper.create_route('Главная', 'MyModuleDashboard', parent=root, icon='Home')
        helper.create_route('Настройки', 'MyModuleSettings', parent=root, icon='Settings')
"""

from django.db.models import Max


class MenuMigrationHelper:
    """
    Хелпер для создания элементов меню в миграциях.
    Автоматически вычисляет order на основе порядка создания.
    """
    
    ORDER_STEP = 10  # Шаг между элементами
    
    def __init__(self, apps, module_source: str):
        """
        Инициализация хелпера.
        
        Args:
            apps: apps из миграции (первый аргумент populate функции)
            module_source: путь к модулю (``modules/<name>`` или ``core/…``)
        """
        self.MenuItem = apps.get_model('cms_adp', 'MenuItem')
        self.MenuSeparator = apps.get_model('cms_adp', 'MenuSeparator')
        self.module_source = module_source
    
    def _get_next_order(self, parent=None) -> int:
        """Возвращает следующий порядок для элементов с указанным родителем."""
        max_order = self.MenuItem.objects.filter(
            parent=parent
        ).aggregate(Max('order'))['order__max']
        return (max_order or 0) + self.ORDER_STEP
    
    def clear_module_items(self):
        """Удаляет все элементы меню этого модуля."""
        self.MenuItem.objects.filter(module_source=self.module_source).delete()
    
    def create_item(
        self,
        name: str,
        item_type: str,
        route_name: str = None,
        icon: str = None,
        parent=None,
        page: str = None,
        external_url: str = None,
        is_active: bool = True,
        is_admin_only: bool = False,
        order: int = None,
    ):
        """
        Создаёт элемент меню.
        
        Args:
            name: Название элемента
            item_type: Тип ('route', 'offcanvas', 'external')
            route_name: Имя маршрута Vue
            icon: Название иконки Lucide
            parent: Родительский элемент
            page: Страница для offcanvas
            external_url: URL для внешних ссылок
            is_active: Активен ли элемент
            is_admin_only: Только для админов
            order: Порядок (если None — вычисляется автоматически)
        
        Returns:
            Созданный MenuItem
        """
        if order is None:
            order = self._get_next_order(parent)
        
        return self.MenuItem.objects.create(
            name=name,
            route_name=route_name,
            icon=icon,
            item_type=item_type,
            page=page,
            external_url=external_url,
            parent=parent,
            order=order,
            is_active=is_active,
            is_admin_only=is_admin_only,
            module_source=self.module_source
        )
    
    def create_route(
        self,
        name: str,
        route_name: str,
        parent=None,
        icon: str = None,
        is_active: bool = True,
        is_admin_only: bool = False,
        order: int = None,
    ):
        """Создаёт элемент-маршрут."""
        return self.create_item(
            name=name,
            item_type='route',
            route_name=route_name,
            icon=icon,
            parent=parent,
            is_active=is_active,
            is_admin_only=is_admin_only,
            order=order,
        )
    
    def create_group(
        self,
        name: str,
        route_name: str = None,
        parent=None,
        icon: str = None,
        is_active: bool = True,
        is_admin_only: bool = False,
        order: int = None,
    ):
        """Создаёт контейнер меню (тип route с опциональным route_name). Обратная совместимость API."""
        return self.create_item(
            name=name,
            item_type='route',
            route_name=route_name,
            icon=icon,
            parent=parent,
            is_active=is_active,
            is_admin_only=is_admin_only,
            order=order,
        )
    
    def create_offcanvas(
        self,
        name: str,
        page: str,
        parent=None,
        icon: str = None,
        is_active: bool = True,
        order: int = None,
    ):
        """Создаёт элемент боковой панели (offcanvas)."""
        return self.create_item(
            name=name,
            item_type='offcanvas',
            icon=icon,
            page=page,
            parent=parent,
            is_active=is_active,
            order=order,
        )
    
    def create_external(
        self,
        name: str,
        url: str,
        parent=None,
        icon: str = None,
        is_active: bool = True,
        order: int = None,
    ):
        """Создаёт внешнюю ссылку."""
        return self.create_item(
            name=name,
            item_type='external',
            icon=icon,
            external_url=url,
            parent=parent,
            is_active=is_active,
            order=order,
        )
    
    def create_separator(
        self,
        name: str,
        before_order: int,
        is_active: bool = True,
    ):
        """Создаёт разделитель меню."""
        return self.MenuSeparator.objects.create(
            name=name,
            before_order=before_order,
            is_active=is_active
        )
    
    def create_routes_batch(
        self,
        items: list,
        parent=None,
        is_active: bool = True,
    ):
        """
        Создаёт несколько маршрутов за раз.
        
        Args:
            items: Список кортежей (name, route_name) или (name, route_name, icon)
            parent: Родительский элемент
            is_active: Активны ли элементы
        
        Returns:
            Список созданных MenuItem
        """
        created = []
        for item in items:
            if len(item) == 2:
                name, route_name = item
                icon = None
            else:
                name, route_name, icon = item
            
            created.append(self.create_route(
                name=name,
                route_name=route_name,
                icon=icon,
                parent=parent,
                is_active=is_active,
            ))
        return created
    
    def create_offcanvas_batch(
        self,
        items: list,
        parent=None,
        is_active: bool = True,
    ):
        """
        Создаёт несколько offcanvas элементов за раз.
        
        Args:
            items: Список кортежей (name, page) или (name, page, icon)
            parent: Родительский элемент
            is_active: Активны ли элементы
        
        Returns:
            Список созданных MenuItem
        """
        created = []
        for item in items:
            if len(item) == 2:
                name, page = item
                icon = None
            else:
                name, page, icon = item
            
            created.append(self.create_offcanvas(
                name=name,
                page=page,
                icon=icon,
                parent=parent,
                is_active=is_active,
            ))
        return created

