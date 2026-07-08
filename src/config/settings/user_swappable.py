"""
AUTH_USER_MODEL включается только после cms_adp.0039_ergo_user_swappable.

Проверка django_migrations выполняется в конце local.py / test.py (после DATABASES),
без django.db.connection — на этапе загрузки settings соединение ещё не готово.
До 0039 остаётся auth.User; ergoms db-migrate применяет 0039 и 0040.
После первого migrate на сервере нужен перезапуск API/worker.
"""

from __future__ import annotations

from typing import Any

ERGO_USER_MIGRATION_APP = 'cms_adp'
ERGO_USER_MIGRATION_NAME = '0039_ergo_user_swappable'
ERGO_USER_MODEL = 'cms_adp.ErgoUser'

_MIGRATION_EXISTS_SQL = """
SELECT EXISTS (
    SELECT 1 FROM django_migrations
    WHERE app = %s AND name = %s
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
                _MIGRATION_EXISTS_SQL,
                [ERGO_USER_MIGRATION_APP, ERGO_USER_MIGRATION_NAME],
            )
            return bool(cursor.fetchone()[0])
    finally:
        conn.close()


def _migration_applied_sqlite(config: dict[str, Any]) -> bool:
    import sqlite3

    conn = sqlite3.connect(config['NAME'], timeout=3)
    try:
        cursor = conn.execute(
            _MIGRATION_EXISTS_SQL.replace('%s', '?'),
            (ERGO_USER_MIGRATION_APP, ERGO_USER_MIGRATION_NAME),
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
