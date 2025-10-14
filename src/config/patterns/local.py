"""
Файл объединяющий локальные настройки для Django-приложения.

Он автоматически импортирует и объединяет настройки из различных модулей конфигурации в папке settings.
"""

import importlib
import sys
from pathlib import Path

# Получаем путь к папке settings
settings_dir = Path(__file__).parent.parent / 'settings'

# Автоматически импортируем все .py файлы из папки settings
for file_path in settings_dir.glob('*.py'):
    if file_path.name != '__init__.py' and file_path.name != '__pycache__':
        module_name = file_path.stem
        module_path = f'src.config.settings.{module_name}'
        
        try:
            module = importlib.import_module(module_path)
            # Импортируем все из модуля
            globals().update({name: getattr(module, name) for name in dir(module) 
                            if not name.startswith('_')})
        except ImportError as e:
            print(f"Ошибка импорта модуля {module_path}: {e}")