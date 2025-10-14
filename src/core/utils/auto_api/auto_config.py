"""
Файл с функциями для автоматизации сборки Django приложений (модулей).
"""

import os
import re
import importlib
import inspect
import logging

from typing import List

from django.apps import AppConfig
from django.urls import (
    include, 
    path
)

from src.config.env import env

logger = logging.getLogger('utils')

def discover_installed_apps(apps_dir: str) -> List[str]:
    """
    Рекурсивно обходит директории и находит установленные приложения, включая подмодули.
    Аргументы:
        apps_dir (str): Базовая директория, в которой находятся приложения.
    Возвращает:
        list: Список строк, представляющих пути к установленным приложениям.
    """
    installed_apps = []

    def recursively_find_apps(current_dir: str, base_module: str) -> None:
        """
        Рекурсивно обходит директории и находит установленные приложения, включая подмодули.
        Аргументы:
            current_dir (str): Текущая директория для обхода.
            base_module (str): Базовый модуль для текущей директории.
        """
        for app_name in os.listdir(current_dir):
            app_path = os.path.join(current_dir, app_name)

            # Проверяем, является ли это директорией
            if os.path.isdir(app_path):
                module_path = f'{base_module}.{app_name}' if base_module else app_name

                # Проверяем наличие файла apps.py
                apps_py_path = os.path.join(app_path, 'apps.py')
                if os.path.exists(apps_py_path):
                    try:
                        # Пытаемся импортировать модуль apps
                        app_module = importlib.import_module(f'src.{module_path}.apps')

                        # Ищем класс AppConfig
                        app_config = None
                        for name, obj in inspect.getmembers(app_module, inspect.isclass):
                            if issubclass(obj, AppConfig) and obj is not AppConfig:
                                app_config = obj
                                break

                        if app_config:
                            installed_apps.append(f'src.{module_path}')
                            logger.debug(f"Найдено приложение: {module_path}")
                    except ModuleNotFoundError:
                        logger.error("Модуль не найден: %s.apps", module_path)
                    except AttributeError:
                        logger.error("Ошибка атрибута: %s.apps не имеет допустимого класса AppConfig", module_path)
                
                # Продолжаем рекурсивный обход независимо от наличия apps.py
                recursively_find_apps(app_path, module_path)

    # Начинаем обход с базовой директории
    recursively_find_apps(apps_dir, os.path.basename(apps_dir))

    return installed_apps

def discover_installed_app_urls(apps_dir: str, prefix: str = None) -> List[str]:
    """
    Рекурсивно обходит директории и находит URL-конфигурации для установленных приложений.

    Аргументы:
        apps_dir (str): Базовая директория, в которой находятся приложения.
        prefix (str): Префикс для импорта модулей (например, "src.modules").

    Возвращает:
        list: Список URL-конфигураций для установленных приложений.
    """
    urlpatterns = []

    def recursively_find_urls(current_dir: str, current_prefix: str, current_route: str = "") -> None:
        """
        Рекурсивно обходит директории и находит URL-конфигурации.

        Аргументы:
            current_dir (str): Текущая директория для обхода.
            current_prefix (str): Текущий префикс для импорта модулей.
            current_route (str): Текущий маршрут, учитывающий иерархию модулей.
        """
        for module_name in os.listdir(current_dir):
            module_path = os.path.join(current_dir, module_name)
            if os.path.isdir(module_path):
                # Проверяем, является ли папка Python-пакетом (имеет __init__.py)
                init_py_path = os.path.join(module_path, '__init__.py')
                if os.path.exists(init_py_path):
                    # Формируем полный путь к модулю
                    module_full_path = f"{current_prefix}.{module_name}" if current_prefix else module_name

                    # Формируем маршрут с учетом иерархии
                    new_route = f"{current_route}{module_name}/"

                    # Проверяем наличие файла urls.py
                    urls_py_path = os.path.join(module_path, 'urls.py')
                    if os.path.exists(urls_py_path):
                        # Формируем маршрут и добавляем его в urlpatterns
                        url_pattern = path(new_route, include(f"{module_full_path}.urls"))
                        urlpatterns.append(url_pattern)

                    # Рекурсивно обходим подмодули
                    recursively_find_urls(module_path, module_full_path, new_route)

    # Начинаем рекурсивный поиск
    recursively_find_urls(apps_dir, prefix, "")

    return urlpatterns

def check_app_config_name(directory: str, config_name: str) -> bool:
    """
    Проверяет все файлы apps.py в указанной директории на наличие определенного названия конфига.

    Аргументы:
        directory (str): Директория, в которой находятся файлы apps.py.
        config_name (str): Название конфига, которое нужно проверить.

    Возвращает:
        bool: True, если конфиг найден, иначе False.
    """
    for root, dirs, files in os.walk(directory):
        for file in files:
            if file == 'apps.py':
                file_path = os.path.join(root, file)

                with open(file_path, 'r', encoding='utf-8') as f:
                    content = f.read()

                    searched_class_signature = rf'class\s+{config_name}Config\s*\(AppConfig\):'
                    if re.search(searched_class_signature, content):
                        return True
    return False

def get_env_deploy_type():
    development = 'src.config.patterns.development'
    production = 'src.config.patterns.production'

    deploy_type = env.str('API_DEPLOY_TYPE', default='development')

    if deploy_type == 'production':
        return production
    else:
        return development
    
def is_valid_module_name(module_name: str) -> bool:
    """
    Проверяет, соответствует ли имя модуля требованиям:
    - только английские буквы в нижнем регистре
    - допустим символ подчеркивания `_`
    - не должно содержать цифр, других символов или букв в верхнем регистре

    Args:
        module_name (str): Имя модуля для проверки

    Returns:
        bool: True, если имя допустимо, иначе False
    """
    # Регулярное выражение для проверки
    pattern = r'^[a-z_]+$'
    return bool(re.match(pattern, module_name))

def discover_modules_apps(modules_dir: str) -> List[str]:
    """
    Обходит директорию modules и находит установленные приложения в структуре <module_name>/api/.
    
    Аргументы:
        modules_dir (str): Базовая директория modules.
        
    Возвращает:
        list: Список строк, представляющих пути к установленным приложениям.
    """
    installed_apps = []
    
    # Обходим все папки в modules_dir
    for module_name in os.listdir(modules_dir):
        module_path = os.path.join(modules_dir, module_name)
        
        # Проверяем, является ли это директорией
        if os.path.isdir(module_path):
            # Проверяем наличие папки api
            api_path = os.path.join(module_path, 'api')
            if os.path.isdir(api_path):
                # Формируем базовый префикс для модуля
                base_module = f'modules.{module_name}.api'
                
                # Рекурсивно ищем приложения в папке api
                def find_apps_in_api(current_dir: str, current_module: str) -> None:
                    # Сначала проверяем apps.py на текущем уровне
                    apps_py_path = os.path.join(current_dir, 'apps.py')
                    if os.path.exists(apps_py_path):
                        try:
                            # Пытаемся импортировать модуль apps
                            import_path = f'{current_module}.apps'
                            app_module = importlib.import_module(import_path)
                            
                            # Ищем класс AppConfig
                            app_config = None
                            for name, obj in inspect.getmembers(app_module, inspect.isclass):
                                if issubclass(obj, AppConfig) and obj is not AppConfig:
                                    app_config = obj
                                    break

                            if app_config:
                                installed_apps.append(current_module)
                                logger.debug(f"Найдено приложение модуля: {current_module}")
                        except ModuleNotFoundError:
                            logger.error("Модуль не найден: %s.apps", current_module)
                        except AttributeError:
                            logger.error("Ошибка атрибута: %s.apps не имеет допустимого класса AppConfig", current_module)
                    
                    # Затем ищем вложенные приложения
                    for app_name in os.listdir(current_dir):
                        app_path = os.path.join(current_dir, app_name)
                        
                        if os.path.isdir(app_path) and app_name != '__pycache__' and not app_name.startswith('.'):
                            # Формируем путь к вложенному модулю
                            nested_module = f'{current_module}.{app_name}'
                            # Рекурсивно проверяем вложенную папку
                            find_apps_in_api(app_path, nested_module)
                
                # Начинаем поиск в папке api
                find_apps_in_api(api_path, base_module)

    return installed_apps

def discover_modules_urls(modules_dir: str) -> List[str]:
    """
    Обходит директорию modules и находит URL-конфигурации в структуре <module_name>/api/.
    
    Аргументы:
        modules_dir (str): Базовая директория modules.
        
    Возвращает:
        list: Список URL-конфигураций для установленных приложений.
    """
    urlpatterns = []
    
    # Обходим все папки в modules_dir
    for module_name in os.listdir(modules_dir):
        module_path = os.path.join(modules_dir, module_name)
        
        # Проверяем, является ли это директорией
        if os.path.isdir(module_path):
            # Проверяем наличие папки api
            api_path = os.path.join(module_path, 'api')
            if os.path.isdir(api_path):
                # Формируем базовый префикс для модуля
                base_module = f'modules.{module_name}.api'
                
                # Рекурсивно ищем urls.py в папке api
                def find_urls_in_api(current_dir: str, current_module: str) -> None:
                    # Сначала проверяем urls.py на текущем уровне
                    urls_py_path = os.path.join(current_dir, 'urls.py')
                    if os.path.exists(urls_py_path):
                        try:
                            # Вычисляем маршрут на основе текущего модуля
                            # Удаляем 'modules.' из начала и заменяем '.api' на '/'
                            route_parts = current_module.replace('modules.', '').replace('.api', '').split('.')
                            route = '/'.join(route_parts) + '/'
                            
                            logger.debug(f"Найден файл urls.py в модуле: {current_module}, маршрут: {route}")
                            url_pattern = path(route, include(f"{current_module}.urls"))
                            urlpatterns.append(url_pattern)
                        except Exception as e:
                            logger.error("Ошибка при добавлении URL для модуля %s: %s", current_module, e)
                    
                    # Затем ищем вложенные urls.py
                    for item_name in os.listdir(current_dir):
                        item_path = os.path.join(current_dir, item_name)
                        
                        if os.path.isdir(item_path) and item_name != '__pycache__' and not item_name.startswith('.'):
                            # Формируем путь к вложенному модулю
                            nested_module = f'{current_module}.{item_name}'
                            # Рекурсивно проверяем вложенную папку
                            find_urls_in_api(item_path, nested_module)
                
                # Начинаем поиск в папке api
                find_urls_in_api(api_path, base_module)

    return urlpatterns