import os
import json
from pathlib import Path

from src.core.cms.models import CMSPage


def get_config_base_path():
    """Получает базовый путь к конфигурациям"""
    return str(Path.cwd().as_posix()).replace('/api', '/client/src/config')

def extract_paths_from_routes_config():
    """Извлекает все пути из routes-config.json"""
    paths = set()
    base_path = get_config_base_path()
    routes_config_path = os.path.join(base_path, 'routes-config.json')
    
    try:
        with open(routes_config_path, 'r', encoding='utf-8') as file:
            routes_config = json.load(file)
            
            # Извлекаем пути из coreRoutes
            if 'coreRoutes' in routes_config:
                for route in routes_config['coreRoutes']:
                    if 'path' in route and route['path'] != '/:pathMatch(.*)*':
                        paths.add(route['path'])
            
            # Извлекаем пути из authRoutes
            if 'authRoutes' in routes_config:
                for route in routes_config['authRoutes']:
                    if 'path' in route:
                        paths.add(route['path'])
            
            # Извлекаем пути из routes
            if 'routes' in routes_config:
                for route_name, route_data in routes_config['routes'].items():
                    if 'path' in route_data:
                        paths.add(route_data['path'])
                        
    except (FileNotFoundError, json.JSONDecodeError) as e:
        print(f"Ошибка при чтении routes-config.json: {e}")
        
    return paths

def create_default_data(apps, schema_editor):
    PermissionMark = apps.get_model('cms', 'PermissionMark')
    CMSPage = apps.get_model('cms', 'CMSPage')

    permission_marks = [
        {'name': 'ComponentAccessionToRead', 'id': 1},
        {'name': 'ComponentAccessionToReadAndWrite', 'id': 2},
        {'name': 'PageAccession', 'id': 3},
        {'name': 'AdminAccession', 'id': 4},
    ]    

    for mark_data in permission_marks:
        PermissionMark.objects.get_or_create(
            id=mark_data['id'],
            defaults={'name': mark_data['name']}
        )

    # Извлекаем пути из routes-config.json
    paths = extract_paths_from_routes_config()

    # Удаляем дубликаты и создаем записи в БД
    unique_paths = list(set(paths))
    for path in unique_paths:
        if path:  # Проверяем что путь не пустой
            CMSPage.objects.get_or_create(path=path)