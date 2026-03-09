# -*- coding: utf-8 -*-
"""
Management command: восстановление меню из populate-функций миграций.

Полностью пересоздаёт меню: сохраняет настройки доступа, очищает MenuItem/MenuSeparator,
вызывает populate из core-миграций и всех установленных модулей (динамическое обнаружение),
восстанавливает allowed_roles и allowed_role_groups.
"""

import importlib
import re

from django.core.management.base import BaseCommand, CommandError
from django.db import migrations

from src.config.settings.base import CORE_DIR, MODULES_DIR
from src.core.cms.adp.menu.models import MenuItem, MenuSeparator

MENU_MARKERS = ('MenuMigrationHelper', 'MenuItem', 'MenuSeparator')

_RE_HELPER_SOURCE = re.compile(r"MenuMigrationHelper\s*\(\s*apps\s*,\s*['\"]([^'\"]+)['\"]")
_RE_DELETE_SOURCE = re.compile(
    r"\.filter\s*\(\s*module_source\s*=\s*['\"]([^'\"]+)['\"]\s*\)\s*\.delete\s*\("
)
_RE_UPDATE_SOURCE = re.compile(
    r"\.filter\s*\(\s*module_source\s*=\s*['\"]([^'\"]+)['\"]\s*\)\s*\.update\s*\("
)


class _MigrationApps:
    """Обёртка для вызова populate-функций миграций вне контекста миграций."""

    def get_model(self, app_label, model_name):
        from django.apps import apps
        return apps.get_model(app_label, model_name)


def _save_access_map():
    """Сохраняет маппинг доступа (route_name, module_source) -> {roles, groups}."""
    access_map = {}
    for item in MenuItem.objects.prefetch_related('allowed_roles', 'allowed_role_groups').all():
        key = (item.route_name or '', item.module_source or '')
        role_ids = list(item.allowed_roles.values_list('id', flat=True))
        group_ids = list(item.allowed_role_groups.values_list('id', flat=True))
        if role_ids or group_ids:
            access_map[key] = {'roles': role_ids, 'groups': group_ids}
    return access_map


def _restore_access_map(access_map):
    """Восстанавливает allowed_roles и allowed_role_groups из access_map."""
    for item in MenuItem.objects.all():
        key = (item.route_name or '', item.module_source or '')
        if key in access_map:
            mapping = access_map[key]
            if mapping.get('roles'):
                item.allowed_roles.set(mapping['roles'])
            if mapping.get('groups'):
                item.allowed_role_groups.set(mapping['groups'])


def _topological_sort(items, dep_fn):
    """
    Топологическая сортировка по графу зависимостей.
    dep_fn(item) -> список элементов, от которых зависит item (должны выполниться раньше).
    """
    result = []
    visited = set()
    temp = set()

    def visit(node):
        if node in temp:
            return
        if node in visited:
            return
        temp.add(node)
        for dep in dep_fn(node):
            visit(dep)
        temp.remove(node)
        visited.add(node)
        result.append(node)

    for item in items:
        visit(item)
    return result


def _discover_core_menu_migrations():
    """
    Сканирует core/cms/adp/migrations/ на наличие data-миграций, затрагивающих меню.
    Фильтрует «аннулированные» миграции:
    - create+delete пары (создание module_source X, а позже полное удаление X)
    - update-миграции для module_source, который не создаётся ни одной оставшейся миграцией
    Возвращает отсортированный по номеру список (stem, func_name, func).
    """
    migrations_dir = CORE_DIR / 'cms' / 'adp' / 'migrations'
    if not migrations_dir.exists():
        return []

    raw = []
    for path in sorted(migrations_dir.glob('*.py')):
        if path.name == '__init__.py':
            continue
        stem = path.stem
        if not stem[0].isdigit():
            continue
        try:
            content = path.read_text(encoding='utf-8')
        except (OSError, UnicodeDecodeError):
            continue
        if not any(marker in content for marker in MENU_MARKERS):
            continue
        try:
            mod = importlib.import_module(f'src.core.cms.adp.migrations.{stem}')
        except (ImportError, ModuleNotFoundError):
            continue

        migration_class = getattr(mod, 'Migration', None)
        if not migration_class or not issubclass(migration_class, migrations.Migration):
            continue

        for op in migration_class.operations:
            if isinstance(op, migrations.RunPython):
                raw.append((stem, op.code.__name__, op.code, content))
                break

    if not raw:
        return []

    stem_creates = {}
    deleted_sources = {}
    stem_update_sources = {}

    for stem, _, _, content in raw:
        sources = set(_RE_HELPER_SOURCE.findall(content))
        if sources:
            stem_creates[stem] = sources
        for source in _RE_DELETE_SOURCE.findall(content):
            deleted_sources[source] = stem
        update_sources = set(_RE_UPDATE_SOURCE.findall(content))
        if update_sources:
            stem_update_sources[stem] = update_sources

    skip_stems = set()
    for stem, sources in stem_creates.items():
        if all(s in deleted_sources for s in sources):
            skip_stems.add(stem)
            for s in sources:
                skip_stems.add(deleted_sources[s])

    effective_sources = set()
    for stem, sources in stem_creates.items():
        if stem not in skip_stems:
            effective_sources.update(sources)

    for stem, sources in stem_update_sources.items():
        if not any(s in effective_sources for s in sources):
            skip_stems.add(stem)

    return [
        (stem, func_name, func)
        for stem, func_name, func, _ in raw
        if stem not in skip_stems
    ]


def _discover_module_menu_migrations():
    """
    Сканирует modules/*/api/migrations/*.py на наличие MenuMigrationHelper.
    Возвращает список (module_name, migration_stem, populate_func) в порядке зависимостей.
    """
    if not MODULES_DIR.exists():
        return []

    module_migrations = {}
    for module_dir in MODULES_DIR.iterdir():
        if not module_dir.is_dir() or module_dir.name.startswith('.'):
            continue
        migrations_dir = module_dir / 'api' / 'migrations'
        if not migrations_dir.exists():
            continue

        menu_migrations = []
        for path in migrations_dir.glob('*.py'):
            if path.name == '__init__.py':
                continue
            try:
                content = path.read_text(encoding='utf-8')
            except (OSError, UnicodeDecodeError):
                continue
            if 'MenuMigrationHelper' not in content:
                continue
            stem = path.stem
            if stem[0].isdigit():
                menu_migrations.append((stem, path))

        if not menu_migrations:
            continue

        menu_migrations.sort(key=lambda x: x[0])
        latest_stem, _ = menu_migrations[-1]
        module_name = module_dir.name

        try:
            mod = importlib.import_module(
                f'modules.{module_name}.api.migrations.{latest_stem}'
            )
        except (ImportError, ModuleNotFoundError):
            continue

        migration_class = getattr(mod, 'Migration', None)
        if not migration_class or not issubclass(migration_class, migrations.Migration):
            continue

        populate_func = None
        for op in migration_class.operations:
            if isinstance(op, migrations.RunPython):
                populate_func = op.code
                break
        if not populate_func:
            continue

        module_migrations[module_name] = (latest_stem, populate_func, migration_class.dependencies)

    if not module_migrations:
        return []

    def get_deps(module_name):
        _, _, deps = module_migrations[module_name]
        result = []
        for dep_app, _ in deps:
            if dep_app in module_migrations and dep_app != module_name:
                result.append(dep_app)
        return result

    sorted_modules = _topological_sort(list(module_migrations.keys()), get_deps)
    return [
        (name, module_migrations[name][0], module_migrations[name][1])
        for name in sorted_modules
    ]


class Command(BaseCommand):
    help = 'Восстанавливает меню из populate-функций core-миграций и установленных модулей'

    def add_arguments(self, parser):
        parser.add_argument(
            '--core-only',
            action='store_true',
            help='Восстановить только core-меню (без модулей)',
        )
        parser.add_argument(
            '--module',
            type=str,
            metavar='NAME',
            help='Восстановить только указанный модуль (core + этот модуль)',
        )
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Показать что будет сделано без записи в БД',
        )

    def handle(self, *args, **options):
        self.dry_run = options['dry_run']
        self.core_only = options['core_only']
        self.module_filter = options.get('module')

        apps = _MigrationApps()
        schema_editor = None

        core_migrations = _discover_core_menu_migrations()

        if self.dry_run:
            access_map = _save_access_map()
            item_count = MenuItem.objects.count()
            sep_count = MenuSeparator.objects.count()
            self.stdout.write(self.style.WARNING(f'[dry-run] Сохранено настроек доступа: {len(access_map)}'))
            self.stdout.write(self.style.WARNING(f'[dry-run] Будет удалено: {item_count} MenuItem, {sep_count} MenuSeparator'))
            for stem, func_name, _ in core_migrations:
                self.stdout.write(self.style.WARNING(f'[dry-run] core: {func_name} ({stem})'))
            discovered = _discover_module_menu_migrations()
            if self.module_filter:
                discovered = [x for x in discovered if x[0] == self.module_filter]
            for name, stem, _ in discovered:
                self.stdout.write(self.style.WARNING(f'[dry-run] Модуль {name}: {stem}'))
            self.stdout.write(self.style.WARNING('[dry-run] БД не изменяется'))
            return

        access_map = _save_access_map()
        self.stdout.write(f'Сохранено настроек доступа: {len(access_map)}')

        MenuItem.objects.all().delete()
        MenuSeparator.objects.all().delete()
        self.stdout.write('Очищены MenuItem и MenuSeparator')

        for stem, func_name, func in core_migrations:
            func(apps, schema_editor)
            self.stdout.write(f'  core: {func_name} ({stem})')

        if not self.core_only:
            discovered = _discover_module_menu_migrations()
            if self.module_filter:
                discovered = [x for x in discovered if x[0] == self.module_filter]
                if not discovered:
                    raise CommandError(f'Модуль "{self.module_filter}" не найден или не имеет меню-миграции')

            for module_name, migration_stem, populate_func in discovered:
                try:
                    populate_func(apps, schema_editor)
                    self.stdout.write(self.style.SUCCESS(f'  {module_name}: {migration_stem}'))
                except Exception as e:
                    self.stderr.write(
                        self.style.ERROR(f'  {module_name}: ошибка — {e}')
                    )
                    raise

        _restore_access_map(access_map)
        self.stdout.write(f'Восстановлено настроек доступа: {len(access_map)}')
        self.stdout.write(self.style.SUCCESS('Готово. Обновите страницу (F5) для отображения меню.'))
