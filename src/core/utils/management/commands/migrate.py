"""
Обёртка над django migrate: перед применением синхронизирует squash
в django_migrations (fake), чтобы после finalize чужим БД хватало
обычного ergoms db-migrate без ручного --fake.
"""
from pathlib import Path

from django.apps import apps
from django.core.management.commands.migrate import Command as DjangoMigrateCommand
from django.db import DEFAULT_DB_ALIAS, connections
from django.db.migrations.loader import MigrationLoader

from src.core.utils.management.commands.sq_del_migrations_lib import (
    discover_squash_files,
    sync_app_squashed_migrations,
)


class Command(DjangoMigrateCommand):
    def handle(self, *args, **options):
        self._sync_squashed_quietly(options.get('verbosity', 1))
        return super().handle(*args, **options)

    def _sync_squashed_quietly(self, verbosity):
        try:
            loader = MigrationLoader(connections[DEFAULT_DB_ALIAS])
        except Exception:
            return

        seen = set()
        recorded_total = 0
        for app_label, _name in loader.disk_migrations:
            if app_label in seen:
                continue
            seen.add(app_label)
            try:
                config = apps.get_app_config(app_label)
            except LookupError:
                continue
            migrations_dir = Path(config.path) / 'migrations'
            if not migrations_dir.is_dir():
                continue
            squash_files = discover_squash_files(migrations_dir)
            if not squash_files:
                continue
            # Orphan-строки чистим только post-finalize (replaces уже снят),
            # иначе не трогаем django_migrations у цепочки до удаления файлов.
            clean_orphans = any(not replaces for _path, replaces in squash_files)
            results = sync_app_squashed_migrations(
                app_label,
                migrations_dir,
                dry_run=False,
                clean_orphans=clean_orphans,
            )
            for item in results:
                if item.get('recorded') or item.get('cleaned') or item.get(
                    'action'
                ) in ('record', 'record_and_clean', 'clean'):
                    recorded_total += 1
                    if verbosity >= 1:
                        self.stdout.write(
                            self.style.SUCCESS(
                                f"[OK] squash sync: {app_label}."
                                f"{item['squash_name']}"
                                + (
                                    f" (cleaned={item['cleaned']})"
                                    if item.get('cleaned')
                                    else ''
                                )
                            )
                        )

        if recorded_total and verbosity >= 1:
            self.stdout.write(
                self.style.SUCCESS(
                    f'[OK] Синхронизировано squash-записей: {recorded_total}'
                )
            )
