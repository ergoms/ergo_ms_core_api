import json
from pathlib import Path

from src.core.cms.models import CMSPage


def get_config_base_path():
    """Получает базовый путь к core/client/src/config относительно расположения скрипта."""
    scripts_dir = Path(__file__).resolve().parent  # core/api/src/core/cms
    core_dir = scripts_dir.parent.parent.parent.parent  # core
    return core_dir / 'client' / 'src' / 'config'

def extract_paths_from_routes_config():
    """Извлекает все пути из routes.js (core/client/src/config)"""
    paths = set()
    base_path = get_config_base_path()
    routes_config_path = base_path / 'routes.js'
    
    try:
        with open(routes_config_path, 'r', encoding='utf-8') as file:
            raw = file.read()
        if raw.strip().startswith('export default'):
            raw = raw.replace('export default', '', 1).strip().rstrip(';').strip()
        routes_config = json.loads(raw)

        if 'coreRoutes' in routes_config:
            for route in routes_config['coreRoutes']:
                if 'path' in route and route['path'] != '/:pathMatch(.*)*':
                    paths.add(route['path'])
        if 'authRoutes' in routes_config:
            for route in routes_config['authRoutes']:
                if 'path' in route:
                    paths.add(route['path'])
        if 'routes' in routes_config:
            for route_name, route_data in routes_config['routes'].items():
                if 'path' in route_data:
                    paths.add(route_data['path'])
                        
    except (FileNotFoundError, json.JSONDecodeError) as e:
        print(f"Ошибка при чтении routes.js: {e}")
        
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

    # Извлекаем пути из routes.js
    paths = extract_paths_from_routes_config()

    # Удаляем дубликаты и создаем записи в БД
    unique_paths = list(set(paths))
    for path in unique_paths:
        if path:  # Проверяем что путь не пустой
            CMSPage.objects.get_or_create(path=path)