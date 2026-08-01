"""
Двухфазное объединение миграций (Django squash).

Фаза create:
  squashmigrations + правка RunPython; старые файлы и django_migrations не трогаем.

Фаза finalize (после ergoms db-migrate на всех инстансах):
  обновить чужие dependencies, удалить replaced-файлы, снять replaces.
"""
from pathlib import Path

from django.apps import apps
from django.core.management import call_command
from django.core.management.base import BaseCommand, CommandError
from django.db import DEFAULT_DB_ALIAS, connection, connections
from django.db.migrations.loader import MigrationLoader

from src.core.utils.management.commands.sq_del_migrations_lib import (
    MANUAL_COPY_MARKER,
    assert_squash_ready_for_finalize,
    collect_external_dependencies,
    collect_statistics,
    find_squash_migration_file,
    fix_runpython_functions,
    inspect_squash_sync_status,
    list_migration_stems,
    read_replaces,
    strip_replaces,
    update_dependencies_in_other_apps,
)


class Command(BaseCommand):
    help = (
        'Объединяет миграции приложения через squash в две фазы: '
        'create (создать squash) и finalize (удалить replaced после migrate).'
    )

    def add_arguments(self, parser):
        parser.add_argument(
            'app_label',
            type=str,
            help='Название приложения (например, cms_adp)',
        )
        parser.add_argument(
            'start_migration',
            type=str,
            nargs='?',
            help='Начальная миграция (по умолчанию первая)',
        )
        parser.add_argument(
            'end_migration',
            type=str,
            nargs='?',
            help='Конечная миграция (по умолчанию последняя)',
        )
        parser.add_argument(
            '--phase',
            choices=('create', 'finalize'),
            default='create',
            help='Фаза: create (по умолчанию) или finalize',
        )
        parser.add_argument(
            '--noinput',
            '--no-input',
            action='store_false',
            dest='interactive',
            help='Не запрашивать подтверждение',
        )
        parser.add_argument(
            '--force',
            action='store_true',
            help=(
                'В finalize: продолжить при внешних зависимостях '
                'без --update-deps (риск поломки графа)'
            ),
        )
        parser.add_argument(
            '--update-deps',
            action='store_true',
            help='В finalize: обновить dependencies в других приложениях',
        )
        parser.add_argument(
            '--check-only',
            action='store_true',
            help='Только отчёт (диапазон, зависимости, applied), без записи',
        )
        parser.add_argument(
            '--squash-name',
            type=str,
            default=None,
            help='Stem squash-файла (для finalize или при нескольких кандидатах)',
        )

    def handle(self, *args, **options):
        app_label = options['app_label']
        phase = options['phase']
        interactive = options.get('interactive', True)
        force = options.get('force', False)
        update_deps = options.get('update_deps', False)
        check_only = options.get('check_only', False)
        squash_name = options.get('squash_name')

        try:
            app_config = apps.get_app_config(app_label)
        except LookupError as exc:
            raise CommandError(f'Приложение "{app_label}" не найдено.') from exc

        migrations_dir = Path(app_config.path) / 'migrations'
        if not migrations_dir.exists():
            raise CommandError(
                f'Директория migrations не найдена для приложения "{app_label}"'
            )

        loader = MigrationLoader(connections[DEFAULT_DB_ALIAS])

        if phase == 'finalize':
            self._handle_finalize(
                app_label=app_label,
                migrations_dir=migrations_dir,
                loader=loader,
                interactive=interactive,
                force=force,
                update_deps=update_deps,
                check_only=check_only,
                squash_name=squash_name,
            )
            return

        start_migration, end_migration, migrations_to_squash = (
            self._resolve_range(app_label, loader, options)
        )
        dependencies_found = collect_external_dependencies(
            loader, app_label, migrations_to_squash
        )
        stats = collect_statistics(
            self.stdout,
            app_label,
            migrations_to_squash,
            loader,
            migrations_dir,
            style=self.style,
        )
        self._print_range_and_stats(
            migrations_to_squash, stats, dependencies_found, phase='create'
        )

        if check_only:
            self.stdout.write(
                self.style.SUCCESS(
                    '\nПроверка завершена. '
                    'Create: ergoms sq-del-migrations '
                    f'{app_label} --phase create\n'
                    'После migrate на всех средах: '
                    f'ergoms sq-del-migrations {app_label} '
                    '--phase finalize --update-deps'
                )
            )
            return

        self._handle_create(
            app_label=app_label,
            migrations_dir=migrations_dir,
            loader=loader,
            start_migration=start_migration,
            end_migration=end_migration,
            migrations_to_squash=migrations_to_squash,
            dependencies_found=dependencies_found,
            interactive=interactive,
            verbosity=options.get('verbosity', 1),
            squash_name=squash_name,
        )

    def _resolve_range(self, app_label, loader, options):
        start_migration = options.get('start_migration')
        end_migration = options.get('end_migration')

        app_migrations = {
            name: migration
            for (app, name), migration in loader.graph.nodes.items()
            if app == app_label
        }
        if not app_migrations:
            raise CommandError(
                f'Миграции не найдены для приложения "{app_label}"'
            )

        if not start_migration:
            start_migration = sorted(app_migrations.keys())[0]
            self.stdout.write(
                f'Начальная миграция не указана, используется: {start_migration}'
            )

        if not end_migration:
            leaf_nodes = [
                name for app, name in loader.graph.leaf_nodes() if app == app_label
            ]
            if leaf_nodes:
                last_migration = None
                max_depth = -1
                for leaf_name in leaf_nodes:
                    try:
                        plan = loader.graph.backwards_plan((app_label, leaf_name))
                        depth = len([m for m in plan if m[0] == app_label])
                        if depth > max_depth:
                            max_depth = depth
                            last_migration = leaf_name
                    except Exception:
                        pass
                end_migration = last_migration or sorted(leaf_nodes)[-1]
            else:
                end_migration = sorted(app_migrations.keys())[-1]
            self.stdout.write(
                f'Конечная миграция не указана, используется последняя: {end_migration}'
            )

        try:
            plan = loader.graph.forwards_plan((app_label, end_migration))
            migrations_to_squash = []
            in_range = False
            for app, name in plan:
                if app != app_label:
                    continue
                if name == start_migration:
                    in_range = True
                if in_range:
                    migrations_to_squash.append(name)
                if name == end_migration:
                    break
        except Exception as e:
            raise CommandError(
                f'Ошибка при определении миграций для объединения: {e}'
            ) from e

        if not migrations_to_squash:
            raise CommandError(
                f'Не найдены миграции для объединения между '
                f'"{start_migration}" и "{end_migration}"'
            )
        return start_migration, end_migration, migrations_to_squash

    def _print_range_and_stats(
        self, migrations_to_squash, stats, dependencies_found, phase
    ):
        self.stdout.write(
            self.style.SUCCESS(
                f'Найдено миграций в диапазоне: {len(migrations_to_squash)}'
            )
        )
        self.stdout.write(f'От: {migrations_to_squash[0]}')
        self.stdout.write(f'До: {migrations_to_squash[-1]}')
        self.stdout.write(f'Фаза: {phase}')

        self.stdout.write('\n' + '=' * 60)
        self.stdout.write(self.style.MIGRATE_HEADING('Статистика:'))
        self.stdout.write('=' * 60)

        label = (
            'Файлов миграций в диапазоне (create не удаляет)'
            if phase == 'create'
            else 'Файлов миграций к удалению в finalize'
        )
        self.stdout.write(f'\n{label}: {stats["migration_files_count"]}')
        if stats['migration_files']:
            for file_name in stats['migration_files'][:10]:
                self.stdout.write(f' - {file_name}')
            if len(stats['migration_files']) > 10:
                self.stdout.write(
                    f' ... и еще {len(stats["migration_files"]) - 10} файлов'
                )

        self.stdout.write(
            f'\nУже applied в django_migrations (не удаляются командой): '
            f'{stats["applied_records_count"]}'
        )
        if stats['applied_records']:
            for record in stats['applied_records'][:10]:
                self.stdout.write(f' - {record}')
            if len(stats['applied_records']) > 10:
                self.stdout.write(
                    f' ... и еще {len(stats["applied_records"]) - 10} записей'
                )

        self.stdout.write(f'\nТаблиц в БД (не затрагиваются): {stats["tables_count"]}')
        if stats['tables']:
            for table in stats['tables'][:10]:
                self.stdout.write(f' - {table}')
            if len(stats['tables']) > 10:
                self.stdout.write(
                    f' ... и еще {len(stats["tables"]) - 10} таблиц'
                )
        self.stdout.write('=' * 60)

        if dependencies_found:
            self.stdout.write(
                self.style.WARNING(
                    f'\nНайдено внешних зависимостей от диапазона: '
                    f'{len(dependencies_found)}'
                )
            )
            for dep in dependencies_found:
                self.stdout.write(
                    f" {dep['app']}.{dep['migration']} "
                    f"({dep['type']}) -> "
                    f"{dep['depends_on'][0]}.{dep['depends_on'][1]}"
                )
            self.stdout.write(
                'В finalize укажите --update-deps, чтобы переписать '
                'dependencies на squash.'
            )

    def _handle_create(
        self,
        *,
        app_label,
        migrations_dir,
        loader,
        start_migration,
        end_migration,
        migrations_to_squash,
        dependencies_found,
        interactive,
        verbosity,
        squash_name,
    ):
        before_stems = list_migration_stems(migrations_dir)

        self.stdout.write('\nСоздание squash миграции...')
        try:
            squash_args = [app_label, start_migration, end_migration]
            call_command(
                'squashmigrations',
                *squash_args,
                verbosity=verbosity,
                interactive=interactive,
            )
        except Exception as e:
            raise CommandError(f'Ошибка при создании squash миграции: {e}') from e

        try:
            squash_file = find_squash_migration_file(
                migrations_dir,
                before_stems=before_stems,
                squash_name=squash_name,
            )
        except CommandError as exc:
            after_stems = list_migration_stems(migrations_dir)
            new_stems = after_stems - before_stems
            if len(new_stems) != 1:
                raise
            candidate = migrations_dir / f'{next(iter(new_stems))}.py'
            if not read_replaces(candidate):
                raise CommandError(
                    f'Новый файл {candidate.name} не содержит replaces.'
                ) from exc
            squash_file = candidate

        self.stdout.write(
            self.style.SUCCESS(f'Squash миграция: {squash_file.name}')
        )

        runpython_ok = fix_runpython_functions(
            self.stdout,
            squash_file,
            migrations_to_squash,
            app_label,
            loader,
            style=self.style,
        )
        content = squash_file.read_text(encoding='utf-8')
        if not runpython_ok or MANUAL_COPY_MARKER in content:
            raise CommandError(
                f'В {squash_file.name} остались функции RunPython, '
                f'требующие ручного копирования. Исправьте файл и повторите '
                f'проверку, затем ergoms db-migrate.'
            )

        if dependencies_found:
            self.stdout.write(
                self.style.WARNING(
                    '\nВнешние зависимости сохранены (create их не меняет). '
                    'После migrate на всех средах: '
                    f'ergoms sq-del-migrations {app_label} '
                    '--phase finalize --update-deps'
                )
            )

        self.stdout.write(
            self.style.SUCCESS(
                '\nФаза create завершена. Старые файлы и django_migrations '
                'не изменялись.\n'
                'Следующие шаги:\n'
                f'1. Проверьте {squash_file.name}\n'
                '2. Закоммитьте squash вместе со старыми миграциями\n'
                '3. На всех средах: ergoms db-migrate\n'
                f'4. Затем: ergoms sq-del-migrations {app_label} '
                '--phase finalize --update-deps'
            )
        )

    def _handle_finalize(
        self,
        *,
        app_label,
        migrations_dir,
        loader,
        interactive,
        force,
        update_deps,
        check_only,
        squash_name,
    ):
        squash_file = find_squash_migration_file(
            migrations_dir,
            before_stems=None,
            squash_name=squash_name,
        )
        replaces = read_replaces(squash_file)
        if not replaces:
            raise CommandError(
                f'В {squash_file.name} нет replaces — finalize не нужен '
                f'или уже выполнен.'
            )

        self.stdout.write(f'Squash: {squash_file.name}')
        self.stdout.write(f'replaces ({len(replaces)}): {replaces[0]} … {replaces[-1]}')

        dependencies_found = collect_external_dependencies(
            loader, app_label, replaces
        )
        stats = collect_statistics(
            self.stdout,
            app_label,
            replaces,
            loader,
            migrations_dir,
            style=self.style,
        )
        self._print_range_and_stats(
            replaces, stats, dependencies_found, phase='finalize'
        )

        sync_status = inspect_squash_sync_status(
            app_label,
            squash_file.stem,
            replaces,
            migrations_dir=migrations_dir,
            db_connection=connection,
        )
        self.stdout.write(
            f"\nГотовность БД: ready_for_finalize="
            f"{sync_status['ready_for_finalize']}"
        )
        self.stdout.write(f"  squash_applied={sync_status['squash_applied']}")
        self.stdout.write(
            f"  missing_replaces={len(sync_status['missing_replaces'])} "
            f"orphans={len(sync_status['orphans'])}"
        )
        self.stdout.write(f"  {sync_status['reason']}")

        if sync_status['can_record_squash'] and not sync_status['squash_applied']:
            self.stdout.write(
                self.style.WARNING(
                    '\nНа этой БД можно синхронизировать squash без схемы:\n'
                    f'  ergoms sync-squashed-migrations --app {app_label}'
                )
            )

        try:
            assert_squash_ready_for_finalize(
                app_label, squash_file.stem, replaces, connection
            )
            self.stdout.write(
                self.style.SUCCESS(
                    'Preflight OK: эта БД готова к finalize.'
                )
            )
            finalize_ready = True
        except CommandError as e:
            finalize_ready = False
            if check_only:
                self.stdout.write(self.style.WARNING(f'Preflight: {e}'))
            else:
                raise

        deps_block = False
        if dependencies_found:
            if not update_deps and not force:
                msg = (
                    f'Найдено {len(dependencies_found)} внешних зависимостей. '
                    f'Укажите --update-deps или --force.'
                )
                deps_block = True
                if check_only:
                    self.stdout.write(self.style.WARNING(msg))
                else:
                    raise CommandError(msg)
            elif force and not update_deps:
                self.stdout.write(
                    self.style.WARNING(
                        '\n--force без --update-deps: чужие dependencies '
                        'не будут обновлены, граф миграций может сломаться.'
                    )
                )

        if check_only:
            if finalize_ready and not deps_block:
                self.stdout.write(
                    self.style.SUCCESS(
                        '\n[READY] Эта БД готова к finalize.\n'
                        'Finalize меняет файлы в репозитории — запускайте '
                        'один раз у разработчика, когда все среды уже сделали '
                        'db-migrate / sync-squashed-migrations:\n'
                        f'  ergoms sq-del-migrations {app_label} '
                        '--phase finalize --update-deps'
                    )
                )
            else:
                self.stdout.write(
                    self.style.WARNING(
                        '\n[NOT READY] Сначала на этой БД:\n'
                        '  ergoms db-migrate\n'
                        '  или ergoms sync-squashed-migrations '
                        f'--app {app_label}\n'
                        'Повторите: ergoms sq-del-migrations '
                        f'{app_label} --phase finalize --check-only'
                    )
                )
            return

        if interactive:
            self.stdout.write(
                self.style.WARNING(
                    '\nВНИМАНИЕ: finalize удалит replaced-файлы миграций '
                    'и снимет replaces. Записи django_migrations не трогаются.'
                )
            )
            response = input('\nПродолжить? (yes/no): ')
            if response.lower() not in ('yes', 'y'):
                self.stdout.write(self.style.ERROR('Отменено пользователем.'))
                return

        if update_deps:
            update_dependencies_in_other_apps(
                self.stdout,
                app_label,
                replaces,
                squash_file.stem,
                loader,
                style=self.style,
            )

        self.stdout.write('\nУдаление replaced-файлов...')
        deleted_count = 0
        for migration_name in replaces:
            migration_file = migrations_dir / f'{migration_name}.py'
            if migration_file.resolve() == squash_file.resolve():
                continue
            if migration_file.exists():
                migration_file.unlink()
                deleted_count += 1
                self.stdout.write(f'Удален файл: {migration_name}.py')

        self.stdout.write(
            self.style.SUCCESS(f'Удалено файлов: {deleted_count}')
        )

        strip_replaces(squash_file)
        self.stdout.write(
            self.style.SUCCESS(f'Снят replaces в {squash_file.name}')
        )

        self.stdout.write(
            self.style.SUCCESS(
                '\nФаза finalize завершена.\n'
                'Проверьте: ergoms api showmigrations '
                f'{app_label}\n'
                'и: ergoms api makemigrations --dry-run\n'
                'Затем закоммитьте изменения.'
            )
        )
