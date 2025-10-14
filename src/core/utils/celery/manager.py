"""
Менеджер для автоматического обнаружения и загрузки конфигураций Celery модулей.
"""

import importlib
import logging

from typing import Dict, Any, List
from pathlib import Path

from src.config.settings.base import MODULES_DIR
from src.core.utils.celery.base import CeleryModuleConfig
from src.core.utils.auto_api.auto_config import discover_installed_apps, discover_modules_apps, is_valid_module_name

class CeleryModuleManager:
    """
    Менеджер для управления конфигурациями Celery модулей.
    Автоматически обнаруживает и загружает конфигурации всех модулей.
    """
    
    def __init__(self):
        self.modules_configs: Dict[str, CeleryModuleConfig] = {}
        self.logger = logging.getLogger('celery.manager')
        self._discover_modules()
    
    def _discover_modules(self):
        """Обнаруживает все Django приложения (модули) и загружает их конфигурации"""
        # Получаем путь к директории модулей
        modules_dir = MODULES_DIR
        
        if not modules_dir.exists():
            self.logger.warning(f"Директория модулей не найдена: {modules_dir}")
            return
        
        # Используем существующий алгоритм для обнаружения Django приложений
        installed_apps = discover_modules_apps(str(modules_dir))
        
        # Также ищем вложенные модули с tasks.py
        nested_modules = self._discover_nested_modules(modules_dir)
        
        # Объединяем все найденные модули
        all_modules = installed_apps + nested_modules
        
        for app_path in all_modules:
            # Извлекаем имя модуля из полного пути
            # Например: 'src.modules.porosity_analysis' -> 'porosity_analysis'
            # Или: 'src.modules.education_materials_parser.fgos' -> 'fgos'
            module_parts = app_path.split('.')
            module_name = module_parts[-1]
            
            # Проверяем валидность имени модуля
            if not is_valid_module_name(module_name):
                self.logger.warning(f"Пропускаем модуль с невалидным именем: {module_name}")
                continue
            
            self._load_module_config(module_name, app_path)
    
    def _load_module_config(self, module_name: str, app_path: str = None):
        """Загружает конфигурацию конкретного модуля"""
        try:
            # Пытаемся импортировать конфигурацию модуля
            config_module_path = f'{app_path}.celery_config' if app_path else f'modules.{module_name}.celery_config'
            config_module = importlib.import_module(config_module_path)
            
            # Ищем класс конфигурации в модуле
            for attr_name in dir(config_module):
                attr = getattr(config_module, attr_name)
                if (isinstance(attr, type) and 
                    issubclass(attr, CeleryModuleConfig) and 
                    attr != CeleryModuleConfig):
                    
                    # Создаем экземпляр конфигурации
                    config_instance = attr(module_name)
                    self.modules_configs[module_name] = config_instance
                    return
        except ImportError as e:
            # Если файл конфигурации не найден, создаем базовую конфигурацию
            self.modules_configs[module_name] = self._create_default_config(module_name, app_path)
        except Exception as e:
            self.logger.error(f"Ошибка загрузки конфигурации модуля {module_name}: {e}")
    
    def _create_default_config(self, module_name: str, app_path: str = None) -> CeleryModuleConfig:
        """Создает базовую конфигурацию для модуля"""
        class DefaultModuleConfig(CeleryModuleConfig):
            def get_task_routes(self) -> Dict[str, str]:
                # Используем полный путь к модулю если он предоставлен
                module_path = app_path if app_path else f'modules.{module_name}'
                return {f'{module_path}.tasks.*': {'queue': module_name}}
            
            def get_task_queues(self) -> Dict[str, Dict[str, Any]]:
                return {
                    module_name: {
                        'exchange': module_name,
                        'routing_key': module_name,
                    }
                }
            
            def get_task_annotations(self) -> Dict[str, Dict[str, Any]]:
                return {}
        
        return DefaultModuleConfig(module_name)
    
    def _discover_nested_modules(self, modules_dir: Path) -> List[str]:
        """Обнаруживает вложенные модули с файлами tasks.py"""
        nested_modules = []
        
        def find_modules_with_tasks(current_dir: Path, base_path: str = ""):
            """Рекурсивно ищет модули с файлами tasks.py"""
            for item in current_dir.iterdir():
                if item.is_dir() and not item.name.startswith('_'):
                    # Проверяем наличие tasks.py
                    tasks_file = item / 'tasks.py'
                    if tasks_file.exists():
                        # Формируем полный путь к модулю
                        module_path = f"{base_path}.{item.name}" if base_path else f"modules.{item.name}"
                        nested_modules.append(module_path)
                        self.logger.debug(f"Найден вложенный модуль с tasks.py: {module_path}")
                    
                    # Рекурсивно обходим поддиректории
                    new_base = f"{base_path}.{item.name}" if base_path else f"modules.{item.name}"
                    find_modules_with_tasks(item, new_base)
        
        find_modules_with_tasks(modules_dir)
        return nested_modules
    
    def get_all_task_routes(self) -> Dict[str, str]:
        """Собирает все маршруты задач из всех модулей"""
        routes = {}
        for config in self.modules_configs.values():
            routes.update(config.get_task_routes())
        return routes
    
    def get_all_task_queues(self) -> Dict[str, Dict[str, Any]]:
        """Собирает все очереди задач из всех модулей"""
        queues = {}
        for config in self.modules_configs.values():
            queues.update(config.get_task_queues())
        return queues
    
    def get_all_task_annotations(self) -> Dict[str, Dict[str, Any]]:
        """Собирает все аннотации задач из всех модулей"""
        annotations = {}
        for config in self.modules_configs.values():
            annotations.update(config.get_task_annotations())
        return annotations
    
    def get_module_loggers(self) -> Dict[str, Dict[str, logging.Logger]]:
        """Собирает все логгеры из всех модулей"""
        loggers = {}
        for module_name, config in self.modules_configs.items():
            loggers[module_name] = config.get_module_loggers()
        return loggers
    
    def get_additional_configs(self) -> Dict[str, Any]:
        """Собирает все дополнительные конфигурации из всех модулей"""
        configs = {}
        for config in self.modules_configs.values():
            configs.update(config.get_additional_config())
        return configs
    
    def get_modules_list(self) -> List[str]:
        """Возвращает список всех загруженных модулей"""
        return list(self.modules_configs.keys())
    
    def get_module_config(self, module_name: str) -> CeleryModuleConfig:
        """Возвращает конфигурацию конкретного модуля"""
        return self.modules_configs.get(module_name) 