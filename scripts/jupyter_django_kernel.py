"""
Django-aware IPython kernel launcher.

Инициализирует Django ORM и автоматически импортирует все модели проекта
и часто используемые утилиты в пользовательское пространство имён notebook.

Используется как entry point ядра 'ergo_django' (kernel.json -> argv).
"""

import os
import sys
from pathlib import Path


def _setup_paths():
    """Добавляет директории проекта в sys.path для импорта Django."""
    project_root = os.environ.get('ERGO_PROJECT_ROOT')
    if not project_root:
        script_dir = Path(__file__).resolve().parent
        api_dir = script_dir.parent
        project_root = str(api_dir.parent.parent)

    api_dir = os.path.join(project_root, 'core', 'api')
    for path in [project_root, api_dir]:
        if path not in sys.path:
            sys.path.insert(0, path)

    return project_root


def _setup_django():
    """Инициализирует Django с development-настройками."""
    os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'src.config.patterns.development')
    os.environ['DJANGO_ALLOW_ASYNC_UNSAFE'] = 'true'
    import django
    django.setup()


def _build_import_blocks():
    """
    Блоки Python-кода для выполнения в user namespace после старта ядра.
    Каждый элемент -- отдельный блок, передаваемый в IPython run_cell.
    """
    model_block = (
        'try:\n'
        '    from django.apps import apps as _apps\n'
        '    _model_count = 0\n'
        '    for _m in _apps.get_models():\n'
        '        globals()[_m.__name__] = _m\n'
        '        _model_count += 1\n'
        '    del _apps\n'
        'except Exception as _e:\n'
        '    _model_count = 0\n'
        '    print(f"Предупреждение: не удалось импортировать модели: {_e}")\n'
    )

    django_utils_block = (
        'from django.db.models import Q, F, Value, Count, Sum, Avg, Min, Max\n'
        'from django.db import connection, connections\n'
        'from django.conf import settings\n'
        'from django.utils import timezone'
    )

    data_block = (
        'try:\n'
        '    import pandas as pd\n'
        '    import numpy as np\n'
        'except ImportError:\n'
        '    pass'
    )

    common_block = (
        'from datetime import datetime, timedelta, date\n'
        'from decimal import Decimal\n'
        'from pathlib import Path\n'
        'from pprint import pprint\n'
        'import json'
    )

    summary_block = (
        'print(f"Django ORM готов. Импортировано моделей: {_model_count}.")\n'
        'print("Утилиты: Q, F, Value, Count, Sum, Avg, Min, Max, pd, np, timezone")\n'
        'del _model_count'
    )

    return [model_block, django_utils_block, data_block, common_block, summary_block]


def main():
    _setup_paths()

    try:
        _setup_django()
    except Exception as e:
        print(f'Предупреждение: не удалось инициализировать Django: {e}')
        print('Ядро запустится без Django ORM.')

    from traitlets.config import Config
    c = Config()
    c.InteractiveShellApp.exec_lines = _build_import_blocks()

    from ipykernel.kernelapp import IPKernelApp
    IPKernelApp.launch_instance(config=c)


if __name__ == '__main__':
    main()
