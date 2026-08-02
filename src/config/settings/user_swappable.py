"""
AUTH_USER_MODEL включается после перехода на ErgoUser.

Маркеры в django_migrations (достаточно любого):
- cms_adp.0039_ergo_user_swappable — до squash;
- cms_adp.0001_initial_squashed_0042_... — после squash sync (0039 очищается).

Проверка выполняется в конце local.py / test.py (после DATABASES),
без django.db.connection — на этапе загрузки settings соединение ещё не готово.
До маркера остаётся auth.User; ergoms db-migrate применяет 0039/0040 или squash.
После первого migrate на сервере нужен перезапуск API/worker.
"""

from __future__ import annotations

from typing import Any

ERGO_USER_MIGRATION_APP = 'cms_adp'
# Обратная совместимость: старое имя до появления списка маркеров.
ERGO_USER_MIGRATION_NAME = '0039_ergo_user_swappable'
ERGO_USER_SQUASH_MIGRATION_NAME = (
    '0001_initial_squashed_0042_drop_graduate_employment_tables'
)
# Любая из записей означает: state уже содержит ErgoUser.
ERGO_USER_APPLIED_MIGRATIONS = (
    ERGO_USER_MIGRATION_NAME,
    ERGO_USER_SQUASH_MIGRATION_NAME,
)
ERGO_USER_MODEL = 'cms_adp.ErgoUser'


def _migration_in_sql(placeholder: str) -> str:
    names = ', '.join(placeholder for _ in ERGO_USER_APPLIED_MIGRATIONS)
    return f"""
SELECT EXISTS (
    SELECT 1 FROM django_migrations
    WHERE app = {placeholder} AND name IN ({names})
)
"""


def _migration_applied_postgresql(config: dict[str, Any]) -> bool:
    import psycopg2

    conn = psycopg2.connect(
        dbname=config['NAME'],
        user=config.get('USER', ''),
        password=config.get('PASSWORD', ''),
        host=config.get('HOST') or None,
        port=config.get('PORT') or None,
        connect_timeout=3,
    )
    try:
        with conn.cursor() as cursor:
            cursor.execute(
                _migration_in_sql('%s'),
                [ERGO_USER_MIGRATION_APP, *ERGO_USER_APPLIED_MIGRATIONS],
            )
            return bool(cursor.fetchone()[0])
    finally:
        conn.close()


def _migration_applied_sqlite(config: dict[str, Any]) -> bool:
    import sqlite3

    conn = sqlite3.connect(config['NAME'], timeout=3)
    try:
        cursor = conn.execute(
            _migration_in_sql('?'),
            (ERGO_USER_MIGRATION_APP, *ERGO_USER_APPLIED_MIGRATIONS),
        )
        return bool(cursor.fetchone()[0])
    finally:
        conn.close()


def ergo_user_migration_applied(databases: dict[str, Any]) -> bool:
    default = databases.get('default') or {}
    engine = default.get('ENGINE', '')

    try:
        if 'postgresql' in engine:
            return _migration_applied_postgresql(default)
        if 'sqlite' in engine:
            return _migration_applied_sqlite(default)
    except Exception:
        return False

    return False


def resolve_auth_user_model(databases: dict[str, Any]) -> str | None:
    if ergo_user_migration_applied(databases):
        return ERGO_USER_MODEL
    return None
