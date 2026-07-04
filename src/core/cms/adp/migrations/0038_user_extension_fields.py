# -*- coding: utf-8 -*-
"""
Поля User (middle_name, public_id) в auth_user без форка Django.

Для БД после форка: колонки уже есть, удаляются записи auth.0013/0014 из django_migrations.
Для чистой установки на PyPI Django: колонки добавляются в auth_user.
"""

import uuid

from django.db import migrations


FORK_AUTH_MIGRATIONS = (
    '0013_add_user_middle_name',
    '0014_add_user_public_id',
)


def _column_exists(cursor, vendor, table_name, column_name):
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


def _add_column_if_missing(cursor, vendor, table_name, column_name, column_sql):
    if _column_exists(cursor, vendor, table_name, column_name):
        return
    if vendor == 'sqlite':
        cursor.execute(f'ALTER TABLE "{table_name}" ADD COLUMN "{column_name}" {column_sql}')
        return
    cursor.execute(f'ALTER TABLE "{table_name}" ADD COLUMN IF NOT EXISTS "{column_name}" {column_sql}')


def ensure_user_extension_columns(apps, schema_editor):
    from django.contrib.auth import get_user_model
    from django.db import connection

    vendor = connection.vendor
    table_name = get_user_model()._meta.db_table

    with connection.cursor() as cursor:
        _add_column_if_missing(
            cursor,
            vendor,
            table_name,
            'middle_name',
            'VARCHAR(150) NULL',
        )
        public_id_sql = 'TEXT NULL' if vendor == 'sqlite' else 'UUID NULL'
        _add_column_if_missing(
            cursor,
            vendor,
            table_name,
            'public_id',
            public_id_sql,
        )

        if vendor == 'postgresql':
            cursor.execute(
                f'CREATE UNIQUE INDEX IF NOT EXISTS auth_user_public_id_uniq ON "{table_name}" (public_id)'
            )
            cursor.execute(
                f'UPDATE "{table_name}" SET public_id = gen_random_uuid() WHERE public_id IS NULL'
            )
        else:
            cursor.execute(f'SELECT id FROM "{table_name}" WHERE public_id IS NULL')
            for (user_id,) in cursor.fetchall():
                cursor.execute(
                    f'UPDATE "{table_name}" SET public_id = %s WHERE id = %s',
                    [str(uuid.uuid4()), user_id],
                )


def remove_fork_auth_migration_records(apps, schema_editor):
    from django.db import connection

    placeholders = ', '.join(['%s'] * len(FORK_AUTH_MIGRATIONS))
    with connection.cursor() as cursor:
        cursor.execute(
            f'DELETE FROM django_migrations WHERE app = %s AND name IN ({placeholders})',
            ['auth', *FORK_AUTH_MIGRATIONS],
        )


def noop_reverse(apps, schema_editor):
    pass


class Migration(migrations.Migration):

    dependencies = [
        ('cms_adp', '0037_consolidate_access_control_menu'),
        ('auth', '0012_alter_user_first_name_max_length'),
    ]

    operations = [
        migrations.RunPython(ensure_user_extension_columns, noop_reverse),
        migrations.RunPython(remove_fork_auth_migration_records, noop_reverse),
    ]
