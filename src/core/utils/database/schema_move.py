"""Перенос отношений PostgreSQL между схемами (без public в целевой архитектуре)."""

from __future__ import annotations

from typing import Iterable

_RELKIND_SQL = {
    'v': 'ALTER VIEW {src}.{name} SET SCHEMA {dest}',
    'm': 'ALTER MATERIALIZED VIEW {src}.{name} SET SCHEMA {dest}',
    'S': 'ALTER SEQUENCE {src}.{name} SET SCHEMA {dest}',
}


def quote_ident(connection, name: str) -> str:
    return connection.ops.quote_name(name)


def list_schema_relations(connection, schema: str, relkinds: Iterable[str]) -> list[tuple[str, str]]:
    kinds = tuple(relkinds)
    if not kinds:
        return []
    placeholders = ', '.join(['%s'] * len(kinds))
    with connection.cursor() as cursor:
        cursor.execute(
            f"""
            SELECT c.relname, c.relkind::text
            FROM pg_class c
            JOIN pg_namespace n ON n.oid = c.relnamespace
            WHERE n.nspname = %s
              AND c.relkind IN ({placeholders})
              AND NOT EXISTS (
                  SELECT 1
                  FROM pg_depend d
                  JOIN pg_extension e ON d.refobjid = e.oid
                  WHERE d.objid = c.oid AND d.deptype = 'e'
              )
              AND NOT (
                  c.relkind = 'S' AND EXISTS (
                      SELECT 1 FROM pg_depend d
                      WHERE d.objid = c.oid AND d.deptype = 'a'
                  )
              )
            """,
            [schema, *kinds],
        )
        return [(row[0], row[1]) for row in cursor.fetchall()]


def list_public_extensions(connection) -> list[str]:
    with connection.cursor() as cursor:
        cursor.execute(
            """
            SELECT e.extname
            FROM pg_extension e
            JOIN pg_namespace n ON n.oid = e.extnamespace
            WHERE n.nspname = 'public'
            ORDER BY 1
            """
        )
        return [row[0] for row in cursor.fetchall()]


def schema_exists(connection, schema: str) -> bool:
    with connection.cursor() as cursor:
        cursor.execute(
            'SELECT 1 FROM pg_namespace WHERE nspname = %s',
            [schema],
        )
        return cursor.fetchone() is not None


def set_relation_schema(connection, relname: str, relkind: str, source: str, dest: str) -> None:
    q_src = quote_ident(connection, source)
    q_dest = quote_ident(connection, dest)
    q_name = quote_ident(connection, relname)
    template = _RELKIND_SQL.get(relkind, 'ALTER TABLE {src}.{name} SET SCHEMA {dest}')
    with connection.cursor() as cursor:
        cursor.execute(template.format(src=q_src, name=q_name, dest=q_dest))


def move_extension_to_schema(connection, extname: str, dest: str) -> None:
    if not extname or not all(ch.isalnum() or ch == '_' for ch in extname):
        return
    q_dest = quote_ident(connection, dest)
    with connection.cursor() as cursor:
        cursor.execute(f'ALTER EXTENSION {extname} SET SCHEMA {q_dest}')


def revoke_create_on_public(connection) -> None:
    with connection.cursor() as cursor:
        cursor.execute('REVOKE CREATE ON SCHEMA public FROM PUBLIC')
        cursor.execute('REVOKE ALL ON SCHEMA public FROM PUBLIC')


def drop_schema_if_exists(connection, schema: str) -> None:
    if not schema or not all(ch.isalnum() or ch == '_' for ch in schema):
        return
    with connection.cursor() as cursor:
        cursor.execute(f'DROP SCHEMA IF EXISTS {schema} CASCADE')


def public_user_object_count(connection) -> int:
    if not schema_exists(connection, 'public'):
        return 0
    with connection.cursor() as cursor:
        cursor.execute(
            """
            SELECT count(*) FROM pg_class c
            JOIN pg_namespace n ON n.oid = c.relnamespace
            WHERE n.nspname = 'public'
              AND c.relkind IN ('r', 'v', 'm', 'p', 'S', 'f')
            """
        )
        return int(cursor.fetchone()[0])
