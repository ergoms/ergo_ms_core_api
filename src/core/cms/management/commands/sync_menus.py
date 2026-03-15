# -*- coding: utf-8 -*-
"""
Management command: синхронизация меню из routes.js модулей.

Парсит modules/<name>/client/js/routes.js и создаёт MenuItem в БД.
Без миграций и без дополнительных конфигов.
"""

import json
import re
from pathlib import Path

from django.core.management.base import BaseCommand, CommandError

from src.core.cms.adp.menu.models import MenuItem
from src.core.utils.auto_api.auto_config import ModuleDiscoverer


def _parse_routes_js(content: str) -> dict:
    """
    Извлекает объект маршрутов из export default { ... }.
    Поддерживает JSON и JS-синтаксис (неэкранированные ключи, одинарные кавычки).
    """
    content = content.strip()
    # Убираем export default
    for prefix in ('export default ', 'export default'):
        if content.startswith(prefix):
            content = content[len(prefix):].strip()
            break
    # Убираем trailing ;
    content = content.rstrip(';').strip()
    try:
        return json.loads(content)
    except json.JSONDecodeError:
        pass
    # Преобразуем JS-объект в JSON: неэкранированные ключи и одинарные кавычки
    content = _js_object_to_json(content)
    try:
        return json.loads(content)
    except json.JSONDecodeError:
        result = {}
        for m in re.finditer(r'["\']?([a-zA-Z_][a-zA-Z0-9_]*)["\']?\s*:\s*\{', content):
            result[m.group(1)] = {'path': '', 'meta': {}}
        return result


def _js_object_to_json(content: str) -> str:
    """Конвертирует JS-объект в валидный JSON (неэкранированные ключи, одинарные кавычки)."""
    # Ключи: { Key: или , Key: -> "Key":
    content = re.sub(r'(\{|\s*,)\s*([a-zA-Z_][a-zA-Z0-9_]*)\s*:', r'\1 "\2":', content)
    # Одинарные кавычки строк -> двойные (простой случай)
    content = re.sub(r"'([^'\\]*(?:\\.[^'\\]*)*)'", lambda m: '"' + m.group(1).replace('\\', '\\\\').replace('"', '\\"') + '"', content)
    # Убираем trailing commas (JSON не поддерживает , перед } или ])
    while re.search(r',\s*[}\]]', content):
        content = re.sub(r',\s*}', '}', content)
        content = re.sub(r',\s*]', ']', content)
    return content


def _is_static_path(path: str) -> bool:
    """Исключаем маршруты с динамическими сегментами (:id, :tab и т.д.)."""
    return path and ':' not in path


class Command(BaseCommand):
    help = 'Синхронизирует меню модулей из routes.js (без миграций)'

    def add_arguments(self, parser):
        parser.add_argument(
            '--module',
            type=str,
            help='Только конкретный модуль (например: video_analysis)',
        )
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Показать изменения без записи в БД',
        )
        parser.add_argument(
            '--list',
            action='store_true',
            help='Показать найденные модули с routes.js',
        )
        parser.add_argument(
            '--name',
            type=str,
            help='Имя группы меню (при --module)',
        )
        parser.add_argument(
            '--icon',
            type=str,
            help='Иконка Lucide для группы (при --module)',
        )
        parser.add_argument(
            '--clear',
            action='store_true',
            help='Удалить все пункты меню (кроме core/cms) перед синхронизацией',
        )

    def handle(self, *args, **options):
        self.dry_run = options['dry_run']
        self.list_only = options['list']
        self.module_filter = options.get('module')
        self.group_name_override = options.get('name')
        self.group_icon_override = options.get('icon')
        self.clear_all = options.get('clear', False)

        discoverer = ModuleDiscoverer()
        modules = discoverer.discover_client_route_modules()

        # Только внешние модули (module:name), не core
        module_paths = {
            k.replace('module:', ''): v
            for k, v in modules.items()
            if k.startswith('module:')
        }

        if self.module_filter:
            if self.module_filter not in module_paths:
                raise CommandError(
                    f'Модуль "{self.module_filter}" не найден или не имеет routes.js. '
                    f'Доступные: {", ".join(sorted(module_paths.keys()))}'
                )
            module_paths = {self.module_filter: module_paths[self.module_filter]}

        if self.list_only:
            self._list_modules(module_paths)
            return

        if self.clear_all and not self.module_filter:
            if self.dry_run:
                count = MenuItem.objects.exclude(module_source='core/cms').count()
                self.stdout.write(f'  [dry-run] --clear: будет удалено {count} пунктов (кроме core/cms)')
            else:
                deleted, _ = MenuItem.objects.exclude(module_source='core/cms').delete()
                self.stdout.write(
                    self.style.WARNING(f'--clear: удалено {deleted} пунктов меню (кроме core/cms)')
                )
                self.stdout.write(self.style.SUCCESS('Готово. Для пересинхронизации запустите sync_menus без --clear.'))
            return

        self.stdout.write(self.style.SUCCESS('Синхронизация меню из routes.js...'))

        for module_name, routes_path in sorted(module_paths.items()):
            self._sync_module(module_name, Path(routes_path))

        if not self.dry_run:
            self.stdout.write(self.style.SUCCESS('Готово.'))
            self.stdout.write(
                self.style.WARNING('Обновите страницу в браузере (F5) для отображения меню.')
            )

    def _list_modules(self, module_paths: dict):
        self.stdout.write(f'Модули с routes.js ({len(module_paths)}):')
        for name in sorted(module_paths.keys()):
            self.stdout.write(f'  - {name}')
        self.stdout.write('')
        self.stdout.write(
            self.style.WARNING(
                'Для добавления пунктов в меню выполните: ergoms api sync_menus '
                '(без --list). Затем обновите страницу в браузере (F5).'
            )
        )

    def _sync_module(self, module_name: str, routes_path: Path):
        module_source = f'modules/{module_name}'

        try:
            content = routes_path.read_text(encoding='utf-8')
        except Exception as e:
            self.stderr.write(self.style.ERROR(f'  {module_name}: не удалось прочитать файл: {e}'))
            return

        routes_data = _parse_routes_js(content)
        if not routes_data:
            self.stdout.write(f'  {module_name}: нет маршрутов, пропуск')
            return

        # Фильтр: только статические пути (без :id и т.п.)
        static_routes = [
            (route_name, data)
            for route_name, data in routes_data.items()
            if _is_static_path(data.get('path', ''))
        ]

        if not static_routes:
            self.stdout.write(f'  {module_name}: нет статических маршрутов, пропуск')
            return

        # Сортируем: первый — с кратчайшим path (корневой)
        static_routes.sort(key=lambda x: (len(x[1].get('path', '')), x[0]))

        root_route_name, root_data = static_routes[0]
        child_routes = static_routes[1:]  # остальные — дочерние

        # --name и --icon применяются только при --module
        group_name = (
            self.group_name_override
            if self.module_filter and self.group_name_override
            else (root_data.get('meta') or {}).get('title') or root_route_name
        )
        group_icon = (
            self.group_icon_override
            if self.module_filter and self.group_icon_override
            else None
        )

        if self.dry_run:
            self.stdout.write(
                f'  [dry-run] {module_name}: группа "{group_name}" ({root_route_name}), '
                f'+{len(child_routes)} дочерних'
            )
            return

        # Удаляем старые пункты модуля
        deleted, _ = MenuItem.objects.filter(module_source=module_source).delete()
        if deleted:
            self.stdout.write(f'  {module_name}: удалено {deleted} старых пунктов')

        # Создаём корневой пункт меню (маршрут с опциональным route_name)
        group = MenuItem.objects.create(
            name=group_name,
            route_name=root_route_name,
            icon=group_icon,
            item_type='route',
            parent=None,
            module_source=module_source,
            is_active=True,
        )

        # Создаём дочерние route-пункты (order вычисляется в save())
        for route_name, data in child_routes:
            meta = data.get('meta') or {}
            display_name = meta.get('title') or route_name
            MenuItem.objects.create(
                name=display_name,
                route_name=route_name,
                icon=None,
                item_type='route',
                parent=group,
                module_source=module_source,
                is_active=True,
            )

        self.stdout.write(
            self.style.SUCCESS(f'  {module_name}: создано 1 группа + {len(child_routes)} пунктов')
        )
