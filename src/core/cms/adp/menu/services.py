"""
Сервис для синхронизации меню с конфигурацией модулей.
Загружает элементы из menu-config.json модулей в БД.
Также синхронизирует разделители из menu-order-config.json.
"""

import os
import json
import logging
from pathlib import Path
from typing import Dict, List, Any, Optional

from django.conf import settings
from .models import MenuItem, MenuSeparator


logger = logging.getLogger(__name__)


class MenuOrderConfigLoader:
    """
    Загрузчик конфигурации порядка меню из menu-order-config.json.
    Используется для импорта разделителей и порядка элементов.
    """
    
    def __init__(self):
        self.base_path = settings.SYSTEM_DIR
        self.config_data = None
    
    def load_config(self) -> Optional[Dict]:
        """
        Загружает конфигурацию из menu-order-config.json.
        Сначала проверяет корень проекта, затем core/client.
        
        Returns:
            Dict с конфигурацией или None
        """
        # Приоритет: корень проекта > core/client/src/config
        config_paths = [
            self.base_path / 'menu-order-config.json',
            self.base_path / 'core' / 'client' / 'src' / 'config' / 'menu-order-config.json'
        ]
        
        for config_path in config_paths:
            if config_path.exists():
                try:
                    with open(config_path, 'r', encoding='utf-8') as f:
                        self.config_data = json.load(f)
                        logger.info(f"Загружена конфигурация порядка меню: {config_path}")
                        return self.config_data
                except json.JSONDecodeError as e:
                    logger.error(f"Ошибка парсинга {config_path}: {e}")
                except Exception as e:
                    logger.error(f"Ошибка чтения {config_path}: {e}")
        
        logger.warning("Файл menu-order-config.json не найден")
        return None
    
    def get_separators(self) -> Dict[str, str]:
        """
        Возвращает разделители из конфигурации.
        
        Returns:
            Dict с разделителями {order_index: name}
        """
        if self.config_data is None:
            self.load_config()
        
        if self.config_data:
            return self.config_data.get('separators', {})
        return {}
    
    def get_menu_order(self) -> List[str]:
        """
        Возвращает порядок элементов меню.
        
        Returns:
            Список имён маршрутов в нужном порядке
        """
        if self.config_data is None:
            self.load_config()
        
        if self.config_data:
            return self.config_data.get('menuOrder', [])
        return []


class MenuSyncService:
    """
    Сервис синхронизации меню с конфигурационными файлами модулей.
    """
    
    def __init__(self):
        # Используем SYSTEM_DIR - корень проекта ergo_ms/
        self.base_path = settings.SYSTEM_DIR
        self.stats = {
            'created': 0,
            'updated': 0,
            'skipped': 0,
            'errors': []
        }
    
    def sync_from_configs(self) -> Dict[str, Any]:
        """
        Синхронизирует меню из всех menu-config.json модулей.
        Также синхронизирует разделители из menu-order-config.json.
        
        Returns:
            Dict с результатами синхронизации
        """
        self.stats = {
            'created': 0, 
            'updated': 0, 
            'skipped': 0, 
            'deleted': 0,
            'errors': [],
            'configs_found': [],
            'separators_created': 0,
            'separators_updated': 0
        }
        
        # Запоминаем ID всех элементов, которые были обновлены/созданы
        self._synced_item_ids = set()
        
        # Ищем все menu-config.json
        configs = self._find_menu_configs()
        
        for config_path, config_data in configs.items():
            self.stats['configs_found'].append(config_path)
            try:
                self._process_config(config_path, config_data)
            except Exception as e:
                logger.error(f"Ошибка обработки {config_path}: {e}")
                self.stats['errors'].append(f"{config_path}: {str(e)}")
        
        # Синхронизируем разделители из menu-order-config.json
        try:
            separator_stats = self._sync_separators_from_order_config()
            self.stats['separators_created'] = separator_stats.get('created', 0)
            self.stats['separators_updated'] = separator_stats.get('updated', 0)
        except Exception as e:
            logger.error(f"Ошибка синхронизации разделителей: {e}")
            self.stats['errors'].append(f"Разделители: {str(e)}")
        
        # Применяем порядок элементов из menu-order-config.json
        try:
            self._apply_menu_order()
        except Exception as e:
            logger.error(f"Ошибка применения порядка меню: {e}")
            self.stats['errors'].append(f"Порядок меню: {str(e)}")
        
        # Удаляем элементы, которые больше не существуют в конфигах
        # (только те, у которых есть module_source — т.е. импортированные)
        try:
            deleted_count = self._cleanup_orphaned_items()
            self.stats['deleted'] = deleted_count
        except Exception as e:
            logger.error(f"Ошибка очистки устаревших элементов: {e}")
            self.stats['errors'].append(f"Очистка: {str(e)}")
        
        return self.stats
    
    def _cleanup_orphaned_items(self) -> int:
        """
        Удаляет элементы меню, которые не были обновлены при синхронизации.
        Удаляются только элементы с module_source (импортированные из конфигов).
        
        Returns:
            Количество удалённых элементов
        """
        if not hasattr(self, '_synced_item_ids') or not self._synced_item_ids:
            return 0
        
        # Получаем все элементы с module_source, которые не были затронуты
        orphaned = MenuItem.objects.filter(
            module_source__isnull=False
        ).exclude(
            id__in=self._synced_item_ids
        )
        
        count = orphaned.count()
        if count > 0:
            logger.info(f"Удаление {count} устаревших элементов меню")
            orphaned.delete()
        
        return count
    
    def _sync_separators_from_order_config(self) -> Dict[str, int]:
        """
        Синхронизирует разделители из menu-order-config.json.
        
        Returns:
            Статистика синхронизации
        """
        stats = {'created': 0, 'updated': 0}
        
        loader = MenuOrderConfigLoader()
        separators_config = loader.get_separators()
        
        if not separators_config:
            logger.info("Разделители в конфигурации не найдены")
            return stats
        
        for order_str, name in separators_config.items():
            try:
                order_index = int(order_str)
                # Преобразуем индекс в before_order (order * 10)
                before_order = order_index * 10
                
                separator, created = MenuSeparator.objects.update_or_create(
                    before_order=before_order,
                    defaults={
                        'name': name,
                        'is_active': True
                    }
                )
                
                if created:
                    stats['created'] += 1
                    logger.info(f"Создан разделитель: {name} (before_order={before_order})")
                else:
                    stats['updated'] += 1
                    logger.info(f"Обновлён разделитель: {name} (before_order={before_order})")
                    
            except (ValueError, TypeError) as e:
                logger.error(f"Ошибка импорта разделителя {order_str}: {e}")
        
        return stats
    
    def _apply_menu_order(self) -> None:
        """
        Применяет порядок элементов меню из menu-order-config.json.
        """
        loader = MenuOrderConfigLoader()
        menu_order = loader.get_menu_order()
        
        if not menu_order:
            logger.info("Порядок меню в конфигурации не найден")
            return
        
        # Обновляем order для корневых элементов согласно menuOrder
        for index, route_name in enumerate(menu_order):
            order_value = index * 10
            updated = MenuItem.objects.filter(
                route_name=route_name,
                parent__isnull=True
            ).update(order=order_value)
            
            if updated:
                logger.info(f"Обновлён порядок для {route_name}: order={order_value}")
    
    def _find_menu_configs(self) -> Dict[str, Dict]:
        """
        Находит все файлы menu-config.json в модулях.
        
        Returns:
            Dict с путями и содержимым конфигов
        """
        configs = {}
        
        logger.info(f"Поиск конфигов меню. Базовый путь: {self.base_path}")
        
        # Ищем в core/client/src/core
        core_path = self.base_path / 'core' / 'client' / 'src' / 'core'
        logger.info(f"Проверка core путь: {core_path}, существует: {core_path.exists()}")
        
        if core_path.exists():
            for module_dir in core_path.iterdir():
                if module_dir.is_dir():
                    config_file = module_dir / 'js' / 'menu-config.json'
                    if config_file.exists():
                        try:
                            with open(config_file, 'r', encoding='utf-8') as f:
                                configs[str(config_file)] = json.load(f)
                                logger.info(f"Найден конфиг: {config_file}")
                        except json.JSONDecodeError as e:
                            logger.error(f"Ошибка парсинга {config_file}: {e}")
        
        # Ищем в modules/*/client
        modules_path = self.base_path / 'modules'
        logger.info(f"Проверка modules путь: {modules_path}, существует: {modules_path.exists()}")
        
        if modules_path.exists():
            for module_dir in modules_path.iterdir():
                if module_dir.is_dir():
                    # Проверяем оба варианта путей: client/js и client/src/js
                    possible_paths = [
                        module_dir / 'client' / 'js' / 'menu-config.json',
                        module_dir / 'client' / 'src' / 'js' / 'menu-config.json',
                    ]
                    
                    for config_file in possible_paths:
                        if config_file.exists():
                            try:
                                with open(config_file, 'r', encoding='utf-8') as f:
                                    configs[str(config_file)] = json.load(f)
                                    logger.info(f"Найден конфиг модуля: {config_file}")
                            except json.JSONDecodeError as e:
                                logger.error(f"Ошибка парсинга {config_file}: {e}")
                            break  # Берём первый найденный конфиг
        
        logger.info(f"Всего найдено конфигов: {len(configs)}")
        return configs
    
    def _process_config(self, config_path: str, config_data: Dict) -> None:
        """
        Обрабатывает конфигурацию меню.
        
        Args:
            config_path: Путь к файлу конфигурации
            config_data: Данные конфигурации
        """
        module_source = self._extract_module_source(config_path)
        menu_sections = config_data.get('menuSections', [])
        
        for section in menu_sections:
            self._process_menu_section(section, module_source, parent=None)
    
    def _extract_module_source(self, config_path: str) -> str:
        """
        Извлекает имя модуля из пути к конфигурации.
        
        Args:
            config_path: Путь к файлу конфигурации
            
        Returns:
            Имя модуля (например: core/cms, modules/bi)
        """
        path = Path(config_path)
        parts = path.parts
        
        if 'modules' in parts:
            idx = parts.index('modules')
            if idx + 1 < len(parts):
                return f"modules/{parts[idx + 1]}"
        
        if 'core' in parts:
            # Ищем после core/client/src/core
            try:
                idx = parts.index('core')
                # Проверяем, это ли путь к модулю в core/client/src/core
                if idx + 4 < len(parts) and parts[idx + 1] == 'client':
                    return f"core/{parts[idx + 4]}"
            except (ValueError, IndexError):
                pass
        
        return 'unknown'
    
    def _process_menu_section(
        self, 
        section: Dict, 
        module_source: str, 
        parent: Optional[MenuItem] = None
    ) -> Optional[MenuItem]:
        """
        Обрабатывает секцию меню рекурсивно.
        
        Args:
            section: Данные секции
            module_source: Источник модуля
            parent: Родительский элемент меню
            
        Returns:
            Созданный/обновлённый элемент меню
        """
        route_name = section.get('routeName')
        name = section.get('title') or section.get('name', '')
        icon = section.get('icon')
        
        if not route_name and not name:
            self.stats['skipped'] += 1
            return None
        
        # Определяем тип элемента
        item_type = 'route'
        page = None
        
        if section.get('isOffcanvas'):
            item_type = 'offcanvas'
            page = section.get('page')
        elif section.get('children') or section.get('list'):
            item_type = 'group'
        
        # Формируем критерии поиска для update_or_create
        # Обычные элементы ищем по route_name + module_source.
        # Для элементов без routeName (например, BI offcanvas вкладки)
        # дополнительно используем name и parent, чтобы не затирать записи.
        lookup = {
            'route_name': route_name,
            'module_source': module_source,
        }
        if route_name is None:
            lookup['name'] = name
            lookup['parent'] = parent
        
        # Ищем или создаём элемент
        item, created = MenuItem.objects.update_or_create(
            defaults={
                'name': name,
                'icon': icon,
                'item_type': item_type,
                'page': page,
                'parent': parent,
                'is_active': True
            },
            **lookup,
        )
        
        # Сохраняем ID для отслеживания (чтобы потом удалить устаревшие)
        if hasattr(self, '_synced_item_ids'):
            self._synced_item_ids.add(item.id)
        
        if created:
            self.stats['created'] += 1
        else:
            self.stats['updated'] += 1
        
        # Обрабатываем дочерние элементы
        children = section.get('children', [])
        for child in children:
            self._process_menu_section(child, module_source, parent=item)
        
        # Обрабатываем список (list) как дочерние элементы
        list_items = section.get('list', [])
        for list_item in list_items:
            self._process_menu_section(list_item, module_source, parent=item)
        
        return item
    
    def get_available_routes(self) -> List[Dict[str, str]]:
        """
        Получает список доступных маршрутов из конфигурации модулей.
        
        Returns:
            Список маршрутов с именем, путём и модулем
        """
        routes = []
        configs = self._find_menu_configs()
        
        for config_path, config_data in configs.items():
            module_source = self._extract_module_source(config_path)
            menu_sections = config_data.get('menuSections', [])
            
            self._extract_routes_recursive(menu_sections, module_source, routes)
        
        return routes
    
    def _extract_routes_recursive(
        self, 
        sections: List[Dict], 
        module_source: str, 
        routes: List[Dict]
    ) -> None:
        """
        Рекурсивно извлекает маршруты из секций.
        
        Args:
            sections: Список секций
            module_source: Источник модуля
            routes: Список для накопления маршрутов
        """
        for section in sections:
            route_name = section.get('routeName')
            name = section.get('title') or section.get('name', '')
            
            if route_name:
                routes.append({
                    'name': route_name,
                    'title': name,
                    'module': module_source
                })
            
            # Рекурсивно обрабатываем дочерние элементы
            children = section.get('children', [])
            self._extract_routes_recursive(children, module_source, routes)
            
            list_items = section.get('list', [])
            self._extract_routes_recursive(list_items, module_source, routes)
    
    def import_separators_from_config(self, config_data: Dict) -> Dict[str, int]:
        """
        Импортирует разделители из конфигурации меню.
        
        Args:
            config_data: Данные конфигурации с separators
            
        Returns:
            Статистика импорта
        """
        stats = {'created': 0, 'updated': 0}
        separators = config_data.get('separators', {})
        
        for order_str, name in separators.items():
            try:
                order = int(order_str)
                # Порядок в конфиге - это индекс, умножаем на 10 для order
                before_order = order * 10
                
                separator, created = MenuSeparator.objects.update_or_create(
                    before_order=before_order,
                    defaults={
                        'name': name,
                        'is_active': True
                    }
                )
                
                if created:
                    stats['created'] += 1
                else:
                    stats['updated'] += 1
                    
            except (ValueError, TypeError) as e:
                logger.error(f"Ошибка импорта разделителя {order_str}: {e}")
        
        return stats

