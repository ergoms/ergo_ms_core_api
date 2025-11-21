"""
Менеджер для автоматического обнаружения и загрузки конфигураций Celery Beat модулей.
"""

import importlib
import logging

from typing import Dict, Any, List
from pathlib import Path

from src.config.settings.base import MODULES_DIR
from src.core.utils.celery_beat.base import CeleryBeatModuleConfig
from src.core.utils.auto_api.auto_config import discover_installed_apps, discover_modules_apps, is_valid_module_name

class CeleryBeatModuleManager:
    """
    Менеджер для управления конфигурациями Celery Beat модулей.
    Автоматически обнаруживает и загружает конфигурации всех модулей.
    """
    
    def __init__(self):
        self.modules_configs: Dict[str, CeleryBeatModuleConfig] = {}
        self.logger = logging.getLogger('celery.beat.manager')
        self._discover_modules()
    
    def _discover_modules(self):
        """Обнаруживает все Django приложения (модули) и загружает их конфигурации Beat"""
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
        """Загружает конфигурацию Beat конкретного модуля"""
        try:
            # Пытаемся импортировать конфигурацию Beat модуля
            config_module_path = f'{app_path}.celery_beat_config' if app_path else f'src.modules.{module_name}.api.celery_beat_config'
            config_module = importlib.import_module(config_module_path)
            
            # Ищем класс конфигурации в модуле
            for attr_name in dir(config_module):
                attr = getattr(config_module, attr_name)
                if (isinstance(attr, type) and 
                    issubclass(attr, CeleryBeatModuleConfig) and 
                    attr != CeleryBeatModuleConfig):
                    
                    # Создаем экземпляр конфигурации
                    config_instance = attr(module_name)
                    self.modules_configs[module_name] = config_instance
                    return        
        except ImportError as e:
            # Если файл конфигурации не найден, создаем базовую конфигурацию
            self.modules_configs[module_name] = self._create_default_config(module_name, app_path)
        except Exception as e:
            self.logger.error(f"Ошибка загрузки конфигурации Beat модуля {module_name}: {e}")
    
    def _create_default_config(self, module_name: str, app_path: str = None) -> CeleryBeatModuleConfig:
        """Создает базовую конфигурацию Beat для модуля"""
        class DefaultBeatModuleConfig(CeleryBeatModuleConfig):
            def get_beat_schedule(self) -> Dict[str, Dict[str, Any]]:
                return {}
        
        return DefaultBeatModuleConfig(module_name)
    
    def _discover_nested_modules(self, modules_dir: Path) -> List[str]:
        """Обнаруживает вложенные модули с файлами tasks.py."""
        nested_modules = []

        def find_modules_with_tasks(current_dir: Path, base_path: str = ""):
            """Рекурсивно ищет модули с файлами tasks.py."""
            for item in current_dir.iterdir():
                if item.is_dir() and not item.name.startswith('_'):
                    # Проверяем наличие tasks.py
                    tasks_file = item / 'tasks.py'
                    if tasks_file.exists():
                        # Формируем полный путь к модулю
                        # Для внешних модулей базовый префикс — 'modules', как и в discover_modules_apps
                        module_path = f"{base_path}.{item.name}" if base_path else f"modules.{item.name}"
                        nested_modules.append(module_path)
                        self.logger.debug(f"Найден вложенный модуль с tasks.py: {module_path}")

                    # Рекурсивно обходим поддиректории
                    new_base = f"{base_path}.{item.name}" if base_path else f"modules.{item.name}"
                    find_modules_with_tasks(item, new_base)

        find_modules_with_tasks(modules_dir)
        return nested_modules
    
    def get_all_beat_schedules(self) -> Dict[str, Dict[str, Any]]:
        """Собирает все расписания задач из всех модулей"""
        schedules = {}
        for config in self.modules_configs.values():
            schedules.update(config.get_beat_schedule())
        return schedules
    
    def get_module_loggers(self) -> Dict[str, Dict[str, logging.Logger]]:
        """Собирает все логгеры Beat из всех модулей"""
        loggers = {}
        for module_name, config in self.modules_configs.items():
            loggers[module_name] = config.get_module_loggers()
        return loggers
    
    def get_additional_beat_configs(self) -> Dict[str, Any]:
        """Собирает все дополнительные конфигурации Beat из всех модулей"""
        configs = {}
        for config in self.modules_configs.values():
            configs.update(config.get_additional_beat_config())
        return configs
    
    def get_modules_list(self) -> List[str]:
        """Возвращает список всех загруженных модулей Beat"""
        return list(self.modules_configs.keys())
    
    def get_module_config(self, module_name: str) -> CeleryBeatModuleConfig:
        """Возвращает конфигурацию Beat конкретного модуля"""
        return self.modules_configs.get(module_name) 