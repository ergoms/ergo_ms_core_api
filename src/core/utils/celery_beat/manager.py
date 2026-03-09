"""
Менеджер для автоматического обнаружения и загрузки конфигураций Celery Beat модулей.

Использует discovered_apps и файловый кэш расписания — при валидном кэше
импорт celery_beat_config модулей не выполняется.
"""

import importlib
import logging
from concurrent.futures import ThreadPoolExecutor, as_completed

from typing import Dict, Any, List, Optional, Tuple

from src.core.utils.celery_beat.base import CeleryBeatModuleConfig
from src.core.utils.auto_api.auto_config import is_valid_module_name
from src.core.utils.auto_api.discovered_apps_cache import get_discovered_apps
from src.core.utils.celery_config_cache import read_beat_schedule_cache, write_beat_schedule_cache


class CeleryBeatModuleManager:
    """
    Менеджер для управления конфигурациями Celery Beat модулей.
    Загружает конфигурации модулей из кэшированного списка discovered_apps.
    """
    
    def __init__(self, use_config_cache: bool = True):
        self.modules_configs: Dict[str, CeleryBeatModuleConfig] = {}
        self.logger = logging.getLogger('celery.beat.manager')
        self._cached_schedule: Optional[Dict[str, Dict[str, Any]]] = (
            read_beat_schedule_cache() if use_config_cache else None
        )
        if self._cached_schedule is None:
            self._load_modules_from_cache()
    
    def _load_modules_from_cache(self) -> None:
        """Загружает конфигурации Beat для модулей из discovered_apps (параллельно)."""
        all_apps = get_discovered_apps()
        module_apps = [app for app in all_apps if app.startswith('modules.')]
        items: List[Tuple[str, str]] = []
        for app_path in module_apps:
            module_parts = app_path.split('.')
            if len(module_parts) >= 3 and module_parts[-1] == 'api':
                module_name = module_parts[-2]
            else:
                module_name = module_parts[-1]
            if not is_valid_module_name(module_name):
                self.logger.warning(f"Пропускаем модуль с невалидным именем: {module_name}")
                continue
            items.append((module_name, app_path))
        max_workers = min(4, len(items) or 1)
        with ThreadPoolExecutor(max_workers=max_workers) as ex:
            futures = {ex.submit(self._load_module_config, name, path): name for name, path in items}
            for future in as_completed(futures):
                result = future.result()
                if result is not None:
                    module_name, config_instance = result
                    self.modules_configs[module_name] = config_instance
        self._save_schedule_to_cache()

    def _load_module_config(self, module_name: str, app_path: Optional[str] = None) -> Optional[Tuple[str, CeleryBeatModuleConfig]]:
        """Загружает конфигурацию Beat конкретного модуля"""
        try:
            # Пытаемся импортировать конфигурацию Beat модуля
            config_module_path = f'{app_path}.celery_beat_config' if app_path else f'src.modules.{module_name}.api.celery_beat_config'
            config_module = importlib.import_module(config_module_path)
            
            for attr_name in dir(config_module):
                attr = getattr(config_module, attr_name)
                if (isinstance(attr, type) and
                    issubclass(attr, CeleryBeatModuleConfig) and
                    attr != CeleryBeatModuleConfig):
                    config_instance = attr(module_name)
                    return (module_name, config_instance)
            return (module_name, self._create_default_config(module_name, app_path))
        except ImportError:
            return (module_name, self._create_default_config(module_name, app_path))
        except Exception as e:
            self.logger.error(f"Ошибка загрузки конфигурации Beat модуля {module_name}: {e}")
            return (module_name, self._create_default_config(module_name, app_path))

    def _save_schedule_to_cache(self) -> None:
        """Сохраняет расписание в кэш после загрузки модулей."""
        schedule = self.get_all_beat_schedules()
        if schedule:
            write_beat_schedule_cache(schedule)

    def _create_default_config(self, module_name: str, app_path: str = None) -> CeleryBeatModuleConfig:
        """Создает базовую конфигурацию Beat для модуля"""
        class DefaultBeatModuleConfig(CeleryBeatModuleConfig):
            def get_beat_schedule(self) -> Dict[str, Dict[str, Any]]:
                return {}
        
        return DefaultBeatModuleConfig(module_name)
    
    def get_all_beat_schedules(self) -> Dict[str, Dict[str, Any]]:
        """Собирает расписания (из кэша или модулей)."""
        if self._cached_schedule is not None:
            return self._cached_schedule
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