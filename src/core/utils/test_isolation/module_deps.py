"""
Утилита для определения зависимостей модуля.

Сканирует импорты в коде модуля и рекурсивно собирает все зависимости
для формирования изолированного INSTALLED_APPS при тестировании.
"""

import ast
import os
import re
from pathlib import Path
from typing import Optional

from src.config.settings.base import MODULES_DIR


def _extract_module_name_from_import(import_path: str) -> Optional[str]:
    """
    Извлекает имя модуля из пути импорта.
    
    Примеры:
        'modules.my_module.api.models' -> 'my_module'
        'modules.my_module.api.serializers' -> 'my_module'
        'src.core.utils' -> None (не модуль)
    """
    if not import_path.startswith('modules.'):
        return None
    
    parts = import_path.split('.')
    if len(parts) >= 2:
        return parts[1]
    return None


def _scan_file_imports(file_path: Path) -> set[str]:
    """
    Сканирует Python файл и возвращает множество импортируемых модулей.
    """
    modules = set()
    
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            content = f.read()
    except (OSError, UnicodeDecodeError):
        return modules
    
    try:
        tree = ast.parse(content)
    except SyntaxError:
        pattern = r'(?:from|import)\s+(modules\.[a-zA-Z_][a-zA-Z0-9_]*)'
        for match in re.finditer(pattern, content):
            module_name = _extract_module_name_from_import(match.group(1))
            if module_name:
                modules.add(module_name)
        return modules
    
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                module_name = _extract_module_name_from_import(alias.name)
                if module_name:
                    modules.add(module_name)
        elif isinstance(node, ast.ImportFrom):
            if node.module:
                module_name = _extract_module_name_from_import(node.module)
                if module_name:
                    modules.add(module_name)
    
    return modules


def _scan_directory_imports(directory: Path) -> set[str]:
    """
    Рекурсивно сканирует директорию и собирает все импорты модулей.
    """
    modules = set()
    
    if not directory.exists():
        return modules
    
    for file_path in directory.rglob('*.py'):
        if '__pycache__' in str(file_path):
            continue
        modules.update(_scan_file_imports(file_path))
    
    return modules


def get_module_dependencies(module_name: str, visited: Optional[set[str]] = None) -> set[str]:
    """
    Возвращает множество имён модулей, от которых зависит данный модуль.
    
    Рекурсивно анализирует зависимости зависимостей.
    
    Args:
        module_name: Имя модуля (например, 'my_module')
        visited: Множество уже посещённых модулей (для предотвращения циклов)
    
    Returns:
        Множество имён модулей-зависимостей
    """
    if visited is None:
        visited = set()
    
    if module_name in visited:
        return set()
    
    visited.add(module_name)
    
    module_api_path = MODULES_DIR / module_name / 'api'
    if not module_api_path.exists():
        return set()
    
    direct_deps = _scan_directory_imports(module_api_path)
    direct_deps.discard(module_name)
    
    all_deps = set(direct_deps)
    for dep in direct_deps:
        if dep not in visited:
            transitive_deps = get_module_dependencies(dep, visited)
            all_deps.update(transitive_deps)
    
    return all_deps


def _get_core_apps() -> list[str]:
    """
    Возвращает список приложений ядра (src.core.*).
    """
    from src.core.utils.auto_api.discovered_apps_cache import _collect_core_apps_fast
    return _collect_core_apps_fast()


def _get_module_apps(module_name: str) -> list[str]:
    """
    Возвращает список всех приложений модуля (включая подмодули).
    
    Примеры:
        'my_module' -> ['modules.my_module.api']
        'my_module' -> ['modules.my_module.api', 'modules.my_module.api.<подраздел>', ...]
    """
    apps = []
    module_api_path = MODULES_DIR / module_name / 'api'
    
    if not module_api_path.exists():
        return apps
    
    if (module_api_path / 'apps.py').exists():
        apps.append(f'modules.{module_name}.api')
    
    for subdir in module_api_path.iterdir():
        if subdir.is_dir() and (subdir / 'apps.py').exists():
            submodule_name = subdir.name
            if submodule_name not in ('__pycache__', 'migrations'):
                apps.append(f'modules.{module_name}.api.{submodule_name}')
    
    return apps


def get_isolated_apps(target_module: str) -> list[str]:
    """
    Формирует список INSTALLED_APPS для изолированного тестирования модуля.
    
    Включает:
    - Все приложения ядра (src.core.*)
    - Целевой модуль (включая все его подмодули)
    - Все зависимости целевого модуля (рекурсивно, включая их подмодули)
    
    Args:
        target_module: Имя целевого модуля (например, 'my_module')
    
    Returns:
        Список путей приложений для INSTALLED_APPS
    """
    core_apps = _get_core_apps()
    
    deps = get_module_dependencies(target_module)
    deps.add(target_module)
    
    module_apps = []
    for module_name in sorted(deps):
        module_apps.extend(_get_module_apps(module_name))
    
    return core_apps + module_apps


def extract_module_from_test_path(test_path: str) -> Optional[str]:
    """
    Извлекает имя модуля из пути теста.
    
    Примеры:
        'modules.my_module.api.tests.TestClass' -> 'my_module'
        'modules.my_module.api.tests' -> 'my_module'
        'src.core.utils.tests' -> None (ядро, не модуль)
    
    Args:
        test_path: Путь к тесту в формате Django
    
    Returns:
        Имя модуля или None если это не модуль
    """
    if not test_path.startswith('modules.'):
        return None
    
    parts = test_path.split('.')
    if len(parts) >= 2:
        return parts[1]
    return None
