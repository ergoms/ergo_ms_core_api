"""
Модуль для автоматического обнаружения Django команд.
"""

import os
import sys

from typing import Dict, List, Type, Optional
from pathlib import Path

import django
from django.core.management import get_commands
from django.apps import apps

from commands.base import PoetryCommand

from src.core.utils.auto_api.auto_config import get_env_deploy_type

class CommandDiscovery:
    """Автоматическое обнаружение Django команд."""
    
    def __init__(self):
        self._commands: Dict[str, Type[PoetryCommand]] = {}
        self._django_initialized = False
    
    def _init_django(self):
        """Инициализация Django."""
        if self._django_initialized:
            return
            
        try:
            project_path = os.path.join(os.path.dirname(__file__), '..', 'src')
            if project_path not in sys.path:
                sys.path.insert(0, project_path)
            
            deploy_type = get_env_deploy_type()
            os.environ.setdefault('DJANGO_SETTINGS_MODULE', deploy_type)
            
            if not django.conf.settings.configured:
                django.setup()
            
            self._django_initialized = True
        except Exception as e:
            print(f"Предупреждение: Не удалось инициализировать Django: {e}")
    
    def _get_builtin_commands(self) -> Dict[str, str]:
        """Получение встроенных Django команд."""
        self._init_django()
        
        try:
            return get_commands()
        except Exception as e:
            print(f"Ошибка при получении Django команд: {e}")
            return {}
    
    def _get_custom_commands(self) -> List[str]:
        """Получение пользовательских команд из приложений."""
        self._init_django()
        
        commands = []
        
        try:
            for app_config in apps.get_app_configs():
                app_path = Path(app_config.path)
                commands_path = app_path / 'management' / 'commands'
                
                if commands_path.exists():
                    for file_path in commands_path.glob('*.py'):
                        if self._is_valid_command_file(file_path):
                            commands.append(file_path.stem)
        except Exception as e:
            print(f"Ошибка при поиске пользовательских команд: {e}")
        
        return commands
    
    def _is_valid_command_file(self, file_path: Path) -> bool:
        """Проверка, является ли файл валидной командой."""
        return (
            file_path.name != '__init__.py' and
            not file_path.name.startswith('__') and
            not file_path.name.endswith('_') and
            file_path.stem not in ['__init__', '__pycache__']
        )
    
    def _create_command_class(self, name: str, is_custom: bool = False) -> Type[PoetryCommand]:
        """Создание класса команды."""
        class_name = f"{name.title().replace('_', '')}Command"
        docstring = f"Команда для '{name}' ({'пользовательская' if is_custom else 'встроенная'})."
        
        return type(
            class_name,
            (PoetryCommand,),
            {
                '__doc__': docstring,
                'poetry_command_name': name,
                'django_command_name': name,
                '__init__': lambda self: super(type(self), self).__init__(name)
            }
        )
    
    def discover(self) -> Dict[str, Type[PoetryCommand]]:
        """Обнаружение всех команд."""
        commands = {}
        
        # Встроенные команды
        builtin_commands = self._get_builtin_commands()
        for name in builtin_commands:
            if not name.startswith('_') and name not in ['__init__', '__pycache__']:
                commands[name] = self._create_command_class(name, is_custom=False)
        
        # Пользовательские команды
        custom_commands = self._get_custom_commands()
        for name in custom_commands:
            if name not in commands:
                commands[name] = self._create_command_class(name, is_custom=True)
        
        self._commands = commands
        return commands
    
    def get_command(self, name: str) -> Optional[Type[PoetryCommand]]:
        """Получение команды по имени."""
        if not self._commands:
            self.discover()
        return self._commands.get(name)
    
    def get_all(self) -> Dict[str, Type[PoetryCommand]]:
        """Получение всех команд."""
        if not self._commands:
            self.discover()
        return self._commands.copy()


# Глобальный экземпляр
discovery = CommandDiscovery() 