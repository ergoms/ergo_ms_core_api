"""
Команда для объединения миграций с проверкой зависимостей.

Процесс:
1. Создает squash миграцию через squashmigrations
2. Проверяет зависимости других приложений на старые миграции
3. Удаляет старые миграции только если нет зависимостей
4. Обновляет зависимости в других приложениях при необходимости
"""
from pathlib import Path

from django.apps import apps
from django.core.management import call_command
from django.core.management.base import BaseCommand, CommandError
from django.db.migrations.loader import MigrationLoader

from src.core.utils.management.commands.sq_del_migrations_lib import (
    collect_statistics,
    fix_runpython_functions,
    update_dependencies_in_other_apps,
)


class Command(BaseCommand):
    help = (
        'Объединяет миграции приложения через squash и удаляет старые файлы. '
        'Проверяет зависимости других приложений перед удалением.'
    )

    def add_arguments(self, parser):
        parser.add_argument(
            'app_label',
            type=str,
            help='Название приложения (например, cms_shortcodes)'
        )
        parser.add_argument(
            'start_migration',
            type=str,
            nargs='?',
            help='Начальная миграция для объединения (по умолчанию 0001_initial). Если не указана, используется первая миграция.'
        )
        parser.add_argument(
            'end_migration',
            type=str,
            nargs='?',
            help='Конечная миграция для объединения (по умолчанию последняя миграция приложения)'
        )
        parser.add_argument(
            '--noinput',
            '--no-input',
            action='store_false',
            dest='interactive',
            help='Не запрашивать подтверждение у пользователя',
        )
        parser.add_argument(
            '--force',
            action='store_true',
            help='Принудительно удалить миграции даже при наличии зависимостей',
        )
        parser.add_argument(
            '--check-only',
            action='store_true',
            help='Только проверить зависимости, не выполнять squash',
        )

    def handle(self, *args, **options):
        app_label = options['app_label']
        start_migration = options.get('start_migration')
        end_migration = options.get('end_migration')
        interactive = options.get('interactive', True)
        force = options.get('force', False)
        check_only = options.get('check_only', False)

        try:
            app_config = apps.get_app_config(app_label)
        except LookupError:
            raise CommandError(f'Приложение "{app_label}" не найдено.')

        app_path = Path(app_config.path)
        migrations_dir = app_path / 'migrations'

        if not migrations_dir.exists():
            raise CommandError(
                f'Директория migrations не найдена для приложения "{app_label}"'
            )

        from django.db import connections, DEFAULT_DB_ALIAS
        loader = MigrationLoader(connections[DEFAULT_DB_ALIAS])

        app_migrations = {}
        for (app, name), migration in loader.graph.nodes.items():
            if app == app_label:
                app_migrations[name] = migration

        if not app_migrations:
            raise CommandError(
                f'Миграции не найдены для приложения "{app_label}"'
            )

        if not start_migration:
            migration_names = sorted(app_migrations.keys())
            start_migration = migration_names[0]
            self.stdout.write(
                f'Начальная миграция не указана, используется: {start_migration}'
            )

        if not end_migration:
            leaf_nodes = loader.graph.leaf_nodes()
            app_leaf_nodes = [name for app, name in leaf_nodes if app == app_label]

            if app_leaf_nodes:
                last_migration = None
                max_depth = -1
                for leaf_name in app_leaf_nodes:
                    try:
                        plan = loader.graph.backwards_plan((app_label, leaf_name))
                        depth = len([m for m in plan if m[0] == app_label])
                        if depth > max_depth:
                            max_depth = depth
                            last_migration = leaf_name
                    except Exception:
                        pass

                if last_migration:
                    end_migration = last_migration
                else:
                    end_migration = sorted(app_leaf_nodes)[-1]
            else:
                end_migration = sorted(app_migrations.keys())[-1]

            self.stdout.write(
                f'Конечная миграция не указана, используется последняя: {end_migration}'
            )

        migrations_to_squash = []
        dependencies_found = []

        try:
            plan = loader.graph.forwards_plan((app_label, end_migration))

            in_range = False
            for app, name in plan:
                if app == app_label:
                    if name == start_migration:
                        in_range = True
                    if in_range:
                        migrations_to_squash.append(name)
                    if name == end_migration:
                        break
        except Exception as e:
            raise CommandError(
                f'Ошибка при определении миграций для объединения: {e}'
            )

        if not migrations_to_squash:
            raise CommandError(
                f'Не найдены миграции для объединения между "{start_migration}" и "{end_migration}"'
            )

        self.stdout.write(
            self.style.SUCCESS(
                f'Найдено миграций для объединения: {len(migrations_to_squash)}'
            )
        )
        self.stdout.write(f'От: {migrations_to_squash[0]}')
        self.stdout.write(f'До: {migrations_to_squash[-1]}')

        self.stdout.write('\nПроверка зависимостей других приложений...')

        for (app_name, migration_name), migration in loader.graph.nodes.items():
            if app_name == app_label:
                continue

            for dep_app, dep_name in migration.dependencies:
                if dep_app == app_label and dep_name in migrations_to_squash:
                    dependencies_found.append({
                        'app': app_name,
                        'migration': migration_name,
                        'depends_on': (app_label, dep_name),
                        'type': 'dependency'
                    })

            for dep_app, dep_name in getattr(migration, 'run_before', []):
                if dep_app == app_label and dep_name in migrations_to_squash:
                    dependencies_found.append({
                        'app': app_name,
                        'migration': migration_name,
                        'depends_on': (app_label, dep_name),
                        'type': 'run_before'
                    })

        stats = collect_statistics(
            self.stdout, app_label, migrations_to_squash, loader, migrations_dir
        )

        self.stdout.write('\n' + '='*60)
        self.stdout.write(self.style.MIGRATE_HEADING('Статистика операции:'))
        self.stdout.write('='*60)

        self.stdout.write(f'\nФайлов миграций для удаления: {stats["migration_files_count"]}')
        if stats['migration_files']:
            for file_name in stats['migration_files'][:10]:
                self.stdout.write(f' - {file_name}')
            if len(stats['migration_files']) > 10:
                self.stdout.write(f' ... и еще {len(stats["migration_files"]) - 10} файлов')

        self.stdout.write(f'\nЗаписей в django_migrations для удаления: {stats["db_records_count"]}')
        if stats['db_records']:
            for record in stats['db_records'][:10]:
                self.stdout.write(f' - {record}')
            if len(stats['db_records']) > 10:
                self.stdout.write(f' ... и еще {len(stats["db_records"]) - 10} записей')

        self.stdout.write(f'\nТаблиц в БД (не будут удалены): {stats["tables_count"]}')
        if stats['tables']:
            for table in stats['tables'][:10]:
                self.stdout.write(f' - {table}')
            if len(stats['tables']) > 10:
                self.stdout.write(f' ... и еще {len(stats["tables"]) - 10} таблиц')

        self.stdout.write('='*60)

        if dependencies_found:
            self.stdout.write(
                self.style.WARNING(
                    f'\nНайдено зависимостей от объединяемых миграций: {len(dependencies_found)}'
                )
            )
            for dep in dependencies_found:
                self.stdout.write(
                    f" {dep['app']}.{dep['migration']} "
                    f"({dep['type']}) -> {dep['depends_on'][0]}.{dep['depends_on'][1]}"
                )
            self.stdout.write(
                '\nDjango автоматически обновит зависимости при применении squash миграции.'
            )

        if not check_only:
            if interactive:
                self.stdout.write(
                    self.style.WARNING(
                        '\nВНИМАНИЕ: Эта операция удалит файлы миграций и записи из БД!'
                    )
                )
                response = input('\nПродолжить? (yes/no): ')
                if response.lower() not in ('yes', 'y'):
                    self.stdout.write(self.style.ERROR('Отменено пользователем.'))
                    return
            else:
                self.stdout.write(
                    self.style.WARNING(
                        '\nПродолжаем с автоматическим обновлением зависимостей...'
                    )
                )

        if check_only:
            self.stdout.write(
                self.style.SUCCESS('\nПроверка завершена. Используйте без --check-only для выполнения.')
            )
            return

        self.stdout.write('\nСоздание squash миграции...')
        try:
            squash_args = [app_label]
            if start_migration:
                squash_args.append(start_migration)
            squash_args.append(end_migration)

            call_command(
                'squashmigrations',
                *squash_args,
                verbosity=options.get('verbosity', 1),
                no_input=not interactive,
            )
            self.stdout.write(
                self.style.SUCCESS('Squash миграция успешно создана.')
            )
        except Exception as e:
            raise CommandError(f'Ошибка при создании squash миграции: {e}')

        existing_migrations = set([
            f.stem for f in migrations_dir.glob('*.py')
            if f.name != '__init__.py' and not f.name.startswith('.')
        ])

        squash_files = list(migrations_dir.glob('*_squashed_*.py'))
        if not squash_files:
            all_files = set([
                f.stem for f in migrations_dir.glob('*.py')
                if f.name != '__init__.py' and not f.name.startswith('.')
            ])
            new_files = all_files - existing_migrations
            if new_files:
                squash_files = [migrations_dir / f'{name}.py' for name in new_files]

        if not squash_files:
            self.stdout.write(
                self.style.WARNING(
                    'Squash миграция не найдена. Возможно, она уже существует или произошла ошибка.'
                )
            )
            return

        squash_file = squash_files[0]
        self.stdout.write(f'Найдена squash миграция: {squash_file.name}')

        fix_runpython_functions(
            self.stdout, squash_file, migrations_to_squash, app_label, loader
        )

        update_dependencies_in_other_apps(
            self.stdout, app_label, migrations_to_squash, squash_file.stem, loader
        )

        self.stdout.write('\nУдаление записей из django_migrations...')
        from django.db import connection

        deleted_db_records = 0
        with connection.cursor() as cursor:
            for migration_name in migrations_to_squash:
                if migration_name == start_migration and start_migration.startswith('0001_'):
                    continue

                cursor.execute(
                    "DELETE FROM django_migrations WHERE app = %s AND name = %s",
                    [app_label, migration_name]
                )
                if cursor.rowcount > 0:
                    deleted_db_records += 1
                    self.stdout.write(f'Удалена запись: {app_label}.{migration_name}')

        self.stdout.write(
            self.style.SUCCESS(
                f'Удалено записей из БД: {deleted_db_records}'
            )
        )

        self.stdout.write('\nУдаление старых файлов миграций...')
        deleted_count = 0

        for migration_name in migrations_to_squash:
            if migration_name == start_migration and start_migration.startswith('0001_'):
                self.stdout.write(
                    f'Пропущена начальная миграция: {migration_name}'
                )
                continue

            migration_file = migrations_dir / f'{migration_name}.py'
            if migration_file.exists():
                migration_file.unlink()
                deleted_count += 1
                self.stdout.write(f'Удален файл: {migration_name}.py')

        self.stdout.write(
            self.style.SUCCESS(
                f'Удалено файлов миграций: {deleted_count}'
            )
        )

        self.stdout.write(
            self.style.SUCCESS(
                '\nОбъединение миграций завершено успешно!\n'
                'Следующие шаги:\n'
                '1. Проверьте созданную squash миграцию\n'
                '2. Примените миграции: python manage.py migrate\n'
                '3. После применения на всех инстансах можно удалить squash миграцию '
                'и оставить только объединенную'
            )
        )
