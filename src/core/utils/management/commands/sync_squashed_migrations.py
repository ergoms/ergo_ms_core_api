"""
Синхронизация записей squash в django_migrations без выполнения операций.

Сценарии:
1. Фаза create (есть replaces): все replaced уже applied → записать squash.
2. После раннего finalize: replaces снят, orphan-записи старых имён →
   записать squash (вместо ручного migrate --fake).

Опционально --clean-orphans удаляет устаревшие строки django_migrations.
"""
from pathlib import Path

from django.apps import apps
from django.core.management.base import BaseCommand, CommandError
from django.db.migrations.loader import MigrationLoader
from django.db import DEFAULT_DB_ALIAS, connections

from src.core.utils.management.commands.sq_del_migrations_lib import (
    discover_squash_files,
    sync_app_squashed_migrations,
)


class Command(BaseCommand):
    help = (
        'Синхронизирует squash-миграции в django_migrations (fake-запись) '
        'для БД, где старая цепочка уже применена.'
    )

    def add_arguments(self, parser):
        parser.add_argument(
            '--app',
            dest='app_labels',
            action='append',
            default=None,
            help='Ограничить приложением (можно указать несколько раз)',
        )
        parser.add_argument(
            '--check-only',
            action='store_true',
            help='Только отчёт, без записи в django_migrations',
        )
        parser.add_argument(
            '--clean-orphans',
            action='store_true',
            help=(
                'После записи squash удалить строки replaces/orphans '
                'из django_migrations'
            ),
        )

    def handle(self, *args, **options):
        app_labels = options.get('app_labels')
        check_only = options.get('check_only', False)
        clean_orphans = options.get('clean_orphans', False)

        loader = MigrationLoader(connections[DEFAULT_DB_ALIAS])
        targets = self._resolve_apps(app_labels, loader)

        if not targets:
            self.stdout.write(
                self.style.WARNING('Не найдено приложений с squash-миграциями.')
            )
            return

        total_record = 0
        total_clean = 0
        need_migrate = []

        for app_label, migrations_dir in targets:
            results = sync_app_squashed_migrations(
                app_label,
                migrations_dir,
                dry_run=check_only,
                clean_orphans=clean_orphans,
            )
            if not results:
                continue

            self.stdout.write(self.style.MIGRATE_HEADING(f'\n=== {app_label} ==='))
            for item in results:
                self.stdout.write(f"  файл: {item['squash_file']}")
                self.stdout.write(f"  статус: {item['reason']}")
                self.stdout.write(
                    f"  squash_applied={item['squash_applied']} "
                    f"ready_for_finalize={item['ready_for_finalize']} "
                    f"action={item['action']}"
                )
                if item['missing_replaces']:
                    sample = ', '.join(item['missing_replaces'][:5])
                    more = len(item['missing_replaces']) - 5
                    suffix = f' … +{more}' if more > 0 else ''
                    self.stdout.write(
                        self.style.WARNING(
                            f'  не хватает replaces: {sample}{suffix}'
                        )
                    )
                    need_migrate.append(app_label)
                if item['action'] in ('record', 'record_and_clean'):
                    total_record += 1
                    label = 'будет записан' if check_only else 'записан'
                    self.stdout.write(
                        self.style.SUCCESS(f'  [{label}] {item["squash_name"]}')
                    )
                if item['cleaned']:
                    total_clean += item['cleaned']
                    label = 'будет удалено orphan' if check_only else 'удалено orphan'
                    self.stdout.write(
                        self.style.SUCCESS(f'  [{label}] {item["cleaned"]}')
                    )

        self.stdout.write('')
        if check_only:
            self.stdout.write(
                self.style.SUCCESS(
                    f'Проверка завершена. К записи squash: {total_record}, '
                    f'к очистке orphan: {total_clean}.\n'
                    'Применить: ergoms sync-squashed-migrations'
                    + (' --clean-orphans' if clean_orphans else '')
                )
            )
        else:
            self.stdout.write(
                self.style.SUCCESS(
                    f'Готово. Записано squash: {total_record}, '
                    f'удалено orphan-записей: {total_clean}.'
                )
            )

        if need_migrate:
            apps_list = ', '.join(sorted(set(need_migrate)))
            self.stdout.write(
                self.style.WARNING(
                    f'\nДля приложений ещё нужен обычный migrate: {apps_list}\n'
                    'ergoms db-migrate'
                )
            )

    def _resolve_apps(self, app_labels, loader):
        """Список (app_label, migrations_dir) для обработки."""
        if app_labels:
            targets = []
            for label in app_labels:
                try:
                    config = apps.get_app_config(label)
                except LookupError as exc:
                    raise CommandError(f'Приложение "{label}" не найдено.') from exc
                migrations_dir = Path(config.path) / 'migrations'
                if not migrations_dir.is_dir():
                    raise CommandError(
                        f'Нет каталога migrations у "{label}"'
                    )
                targets.append((label, migrations_dir))
            return targets

        # Только apps, где на диске есть squash-файлы
        seen = set()
        targets = []
        for app_label, _name in loader.disk_migrations:
            if app_label in seen:
                continue
            seen.add(app_label)
            try:
                config = apps.get_app_config(app_label)
            except LookupError:
                continue
            migrations_dir = Path(config.path) / 'migrations'
            if migrations_dir.is_dir() and discover_squash_files(migrations_dir):
                targets.append((app_label, migrations_dir))
        return sorted(targets, key=lambda item: item[0])
