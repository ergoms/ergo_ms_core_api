"""
Менеджер для автоматического обнаружения и загрузки конфигураций Celery модулей.
"""

import importlib
import logging

from typing import Dict, Any, List, Optional
from pathlib import Path

from src.config.settings.base import MODULES_DIR
from src.core.utils.celery.base import CeleryModuleConfig
from src.core.utils.auto_api.auto_config import ModuleDiscoverer, is_valid_module_name

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
        
        # Обнаруживаем Django приложения модулей через ModuleDiscoverer
        discoverer = ModuleDiscoverer()
        installed_apps: List[str] = []
        discoverer._find_modules_apps(str(modules_dir), installed_apps)
        
        # Также ищем вложенные модули с tasks.py
        nested_modules = self._discover_nested_modules(modules_dir)
        
        # Объединяем все найденные модули
        all_modules = installed_apps + nested_modules
        
        for app_path in all_modules:
            # Извлекаем имя модуля из полного пути
            # Например: 'modules.porosity_analysis.api' -> 'porosity_analysis'
            # Или: 'modules.education_materials_parser.fgos' -> 'fgos'
            # Или: 'modules.impuls_analysis.api' -> 'impuls_analysis'
            module_parts = app_path.split('.')
            
            # Если путь заканчивается на '.api', берем предпоследнюю часть
            # Иначе берем последнюю часть
            if len(module_parts) >= 3 and module_parts[-1] == 'api':
                module_name = module_parts[-2]  # Берем имя модуля перед 'api'
            else:
                module_name = module_parts[-1]  # Берем последнюю часть
            
            # Проверяем валидность имени модуля
            if not is_valid_module_name(module_name):
                self.logger.warning(f"Пропускаем модуль с невалидным именем: {module_name} (путь: {app_path})")
                continue
            
            self._load_module_config(module_name, app_path)
    
    def _load_module_config(self, module_name: str, app_path: Optional[str] = None):
        """Загружает конфигурацию конкретного модуля"""
        # Формируем путь к конфигурации
        config_module_path = f'{app_path}.celery_config' if app_path else f'modules.{module_name}.celery_config'
        
        try:
            self.logger.debug(f"Попытка загрузки конфигурации Celery для модуля {module_name} по пути: {config_module_path}")
            config_module = importlib.import_module(config_module_path)
            
            # Ищем класс конфигурации в модуле
            config_class = None
            for attr_name in dir(config_module):
                attr = getattr(config_module, attr_name)
                if (isinstance(attr, type) and 
                    issubclass(attr, CeleryModuleConfig) and 
                    attr != CeleryModuleConfig):
                    config_class = attr
                    break
            
            if config_class:
                # Создаем экземпляр конфигурации
                config_instance = config_class(module_name)
                self.modules_configs[module_name] = config_instance
                self.logger.debug(f"Успешно загружена конфигурация Celery для модуля {module_name}")
                return
            else:
                # Отсутствие класса конфигурации - нормальная ситуация, используем дефолт
                self.logger.debug(f"В модуле {config_module_path} не найден класс конфигурации Celery, создается дефолтная конфигурация")
                self.modules_configs[module_name] = self._create_default_config(module_name, app_path)
        except ImportError as e:
            # Если файл конфигурации не найден - это нормальная ситуация, не все модули имеют celery_config
            self.logger.debug(f"Модуль {module_name} не имеет celery_config (путь: {config_module_path}), создается дефолтная конфигурация")
            self.modules_configs[module_name] = self._create_default_config(module_name, app_path)
        except Exception as e:
            self.logger.error(f"Ошибка загрузки конфигурации модуля {module_name}: {e}", exc_info=True)
            # При любой другой ошибке также создаем дефолтную конфигурацию
            self.modules_configs[module_name] = self._create_default_config(module_name, app_path)
    
    def _create_default_config(self, module_name: str, app_path: Optional[str] = None) -> CeleryModuleConfig:
        """Создает базовую конфигурацию для модуля"""
        class DefaultModuleConfig(CeleryModuleConfig):
            def get_task_routes(self) -> Dict[str, Dict[str, Any]]:
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
    
    def get_module_config(self, module_name: str) -> Optional[CeleryModuleConfig]:
        """Возвращает конфигурацию конкретного модуля"""
        return self.modules_configs.get(module_name)
    
    def get_all_queue_limits(self) -> Dict[str, int]:
        """
        Собирает лимиты параллелизма для всех очередей из всех модулей.
        
        Returns:
            Dict[str, int]: Словарь {имя_очереди: max_concurrent_tasks}
        """
        limits = {}
        for module_name, config in self.modules_configs.items():
            max_concurrent = config.get_max_concurrent_tasks()
            if max_concurrent > 0:
                queue_name = config.get_queue_name()
                limits[queue_name] = max_concurrent
                self.logger.debug(
                    f"Модуль {module_name}: очередь {queue_name}, "
                    f"max_concurrent_tasks={max_concurrent}"
                )
        return limits
    
    def setup_queue_concurrency(self):
        """
        Настраивает менеджер параллелизма очередей на основе конфигураций модулей.
        Должен вызываться после инициализации Celery.
        """
        from src.core.utils.celery.concurrency import queue_concurrency_manager
        
        limits = self.get_all_queue_limits()
        for queue_name, max_concurrent in limits.items():
            queue_concurrency_manager.set_queue_limit(queue_name, max_concurrent)
        
        self.logger.info(
            f"Настроено ограничение параллелизма для {len(limits)} очередей: "
            f"{', '.join(f'{q}={l}' for q, l in limits.items())}"
        ) 