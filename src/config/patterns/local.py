"""
Файл объединяющий локальные настройки для Django-приложения.

Импортирует настройки из settings. Модули celery_beat и celery
загружаются только для соответствующих процессов (отложенная загрузка).
"""

import importlib
import sys
from pathlib import Path

settings_dir = Path(__file__).parent.parent / 'settings'

argv_joined = ' '.join(sys.argv).lower()
is_celery_beat = 'beat' in argv_joined
is_jupyter_cmd = 'jupyter' in argv_joined or 'notebook' in argv_joined

deferred_settings = set()
if not is_celery_beat:
    deferred_settings.add('celery_beat')
if not is_jupyter_cmd:
    deferred_settings.add('jupyter')

for file_path in settings_dir.glob('*.py'):
    if file_path.name in ('__init__.py', '__pycache__'):
        continue
    module_name = file_path.stem
    if module_name in deferred_settings:
        continue
    module_path = f'src.config.settings.{module_name}'
    try:
        module = importlib.import_module(module_path)
        globals().update({
            name: getattr(module, name)
            for name in dir(module)
            if not name.startswith('_')
        })
    except ImportError as e:
        print(f"Ошибка импорта модуля {module_path}: {e}")

from src.config.settings.user_swappable import resolve_auth_user_model

_resolved_auth_user_model = resolve_auth_user_model(DATABASES)
if _resolved_auth_user_model:
    AUTH_USER_MODEL = _resolved_auth_user_model