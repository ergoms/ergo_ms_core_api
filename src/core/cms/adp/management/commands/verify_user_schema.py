# -*- coding: utf-8 -*-
"""
Pre-flight проверка схемы auth_user / ErgoUser.

Запуск: ergoms api verify_user_schema
"""

from __future__ import annotations

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError
from django.db import connection


REQUIRED_COLUMNS = ('middle_name', 'public_id')
MIGRATION_0038 = ('cms_adp', '0038_user_extension_fields')
MIGRATION_0039 = ('cms_adp', '0039_ergo_user_swappable')
MIGRATION_0040 = ('cms_adp', '0040_migrate_user_content_type')
MIGRATION_SQUASH = (
    'cms_adp',
    '0001_initial_squashed_0042_drop_graduate_employment_tables',
)

ORPHAN_FK_CHECKS = (
    ('cms_adp_userprofile', 'user_id'),
    ('cms_adp_userrole', 'user_id'),
)


def _table_exists(cursor, vendor: str, table_name: str) -> bool:
    if vendor == 'sqlite':
        cursor.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name=%s",
            [table_name],
        )
        return cursor.fetchone() is not None
    if vendor == 'postgresql':
        cursor.execute(
            """
            SELECT EXISTS (
                SELECT 1
                FROM information_schema.tables
                WHERE table_schema = CURRENT_SCHEMA()
                  AND table_name = %s
            )
            """,
            [table_name],
        )
        return cursor.fetchone()[0]
    return False


def _column_exists(cursor, vendor: str, table_name: str, column_name: str) -> bool:
    if vendor == 'sqlite':
        cursor.execute(f'PRAGMA table_info("{table_name}")')
        return any(col[1] == column_name for col in cursor.fetchall())
    if vendor == 'postgresql':
        cursor.execute(
            """
            SELECT EXISTS (
                SELECT 1
                FROM information_schema.columns
                WHERE table_schema = CURRENT_SCHEMA()
                  AND table_name = %s
                  AND column_name = %s
            )
            """,
            [table_name, column_name],
        )
        return cursor.fetchone()[0]
    return False


class Command(BaseCommand):
    help = (
        'Проверяет схему auth_user (middle_name, public_id), counts пользователей '
        'и orphan FK для ErgoUser.'
    )

    def add_arguments(self, parser):
        parser.add_argument(
            '--strict-public-id',
            action='store_true',
            help='Завершить с ошибкой, если у пользователей нет public_id.',
        )

    def handle(self, *args, **options):
        errors: list[str] = []
        vendor = connection.vendor
        user_model = get_user_model()
        table_name = user_model._meta.db_table

        self.stdout.write(f'Модель пользователя: {user_model._meta.label}')
        self.stdout.write(f'Таблица: {table_name} (БД: {vendor})')

        if user_model._meta.label_lower != 'cms_adp.ergouser':
            errors.append(
                f'Ожидается cms_adp.ErgoUser, сейчас {user_model._meta.label}. '
                'Проверьте AUTH_USER_MODEL = cms_adp.ErgoUser.'
            )

        if not self._ergo_user_schema_ready():
            errors.append(
                'Переход на ErgoUser не зафиксирован в django_migrations '
                f'(ожидается {MIGRATION_0038[1]}+{MIGRATION_0039[1]}+{MIGRATION_0040[1]} '
                f'либо squash {MIGRATION_SQUASH[1]}). '
                'Выполните: ergoms db-migrate'
            )

        with connection.cursor() as cursor:
            if not _table_exists(cursor, vendor, table_name):
                errors.append(f'Таблица {table_name} не найдена.')
            else:
                for column in REQUIRED_COLUMNS:
                    if not _column_exists(cursor, vendor, table_name, column):
                        errors.append(
                            f'Колонка {table_name}.{column} отсутствует. '
                            'Выполните: ergoms db-migrate'
                        )

                stats = self._fetch_user_stats(cursor, table_name)
                self.stdout.write('')
                self.stdout.write('Counts:')
                self.stdout.write(f'  total_users: {stats["total"]}')
                self.stdout.write(f'  public_id_null: {stats["public_id_null"]}')
                self.stdout.write(f'  middle_name_filled: {stats["middle_name_filled"]}')

                if options['strict_public_id'] and stats['public_id_null']:
                    errors.append(
                        f'У {stats["public_id_null"]} пользователей public_id IS NULL.'
                    )

                for child_table, fk_column in ORPHAN_FK_CHECKS:
                    if not _table_exists(cursor, vendor, child_table):
                        continue
                    orphan_count = self._count_orphan_fk(
                        cursor,
                        child_table,
                        fk_column,
                        table_name,
                    )
                    self.stdout.write(f'  orphan_{child_table}: {orphan_count}')
                    if orphan_count:
                        errors.append(
                            f'Orphan FK: {child_table}.{fk_column} → {orphan_count} строк без user.'
                        )

        ct_label = self._user_content_type_label()
        self.stdout.write(f'  content_type: {ct_label}')

        if errors:
            self.stdout.write('')
            for message in errors:
                self.stderr.write(self.style.ERROR(message))
            raise CommandError(f'Проверка не пройдена ({len(errors)} ошибок).')

        self.stdout.write(self.style.SUCCESS('Проверка пройдена.'))

    def _migration_applied(self, migration: tuple[str, str]) -> bool:
        with connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT EXISTS (
                    SELECT 1 FROM django_migrations
                    WHERE app = %s AND name = %s
                )
                """,
                migration,
            )
            return cursor.fetchone()[0]

    def _ergo_user_schema_ready(self) -> bool:
        if self._migration_applied(MIGRATION_SQUASH):
            return True
        return all(
            self._migration_applied(m)
            for m in (MIGRATION_0038, MIGRATION_0039, MIGRATION_0040)
        )

    def _fetch_user_stats(self, cursor, table_name: str) -> dict:
        cursor.execute(f'SELECT COUNT(*) FROM "{table_name}"')
        total = cursor.fetchone()[0]
        cursor.execute(
            f'SELECT COUNT(*) FROM "{table_name}" WHERE public_id IS NULL'
        )
        public_id_null = cursor.fetchone()[0]
        cursor.execute(
            f"""
            SELECT COUNT(*) FROM "{table_name}"
            WHERE middle_name IS NOT NULL AND TRIM(middle_name) <> ''
            """
        )
        middle_name_filled = cursor.fetchone()[0]
        return {
            'total': total,
            'public_id_null': public_id_null,
            'middle_name_filled': middle_name_filled,
        }

    def _count_orphan_fk(
        self,
        cursor,
        child_table: str,
        fk_column: str,
        user_table: str,
    ) -> int:
        cursor.execute(
            f"""
            SELECT COUNT(*)
            FROM "{child_table}" c
            LEFT JOIN "{user_table}" u ON u.id = c."{fk_column}"
            WHERE c."{fk_column}" IS NOT NULL AND u.id IS NULL
            """
        )
        return cursor.fetchone()[0]

    def _user_content_type_label(self) -> str:
        try:
            from django.contrib.contenttypes.models import ContentType

            user_model = get_user_model()
            ct = ContentType.objects.get_for_model(user_model)
            return f'{ct.app_label}.{ct.model}'
        except Exception as exc:
            return f'unknown ({exc})'
