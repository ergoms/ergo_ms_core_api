from collections import OrderedDict
from contextlib import contextmanager
from typing import Any, Tuple, Union

from django.db import connection
from django.db.backends.utils import CursorWrapper

from sqlalchemy.dialects import postgresql
from sqlalchemy.sql import ClauseElement

from .types import (
    RawSQL,
    Callable,
    ListOrderedDict,
    Columns,
    FetchResult,
)


class BaseQueryExecutor:
    @classmethod
    def get_raw_sql(cls, get_query: Callable, *args, **kwargs) -> RawSQL:
        sql, params = "", ()
        try:
            sql, params = get_query(*args, **kwargs)
        except ValueError:
            sql = get_query()
        return sql, params

    @classmethod
    def fetchall(cls, get_query: Callable, *args, **kwargs):
        pass

    @classmethod
    def fetchone(cls, get_query, *args, **kwargs):
        pass

    @classmethod
    def execute(cls, get_query, *args, **kwargs):
        pass


class QueryExecutor(BaseQueryExecutor):
    @classmethod
    def _get_many_result(cls, cursor: CursorWrapper) -> FetchResult:
        return cursor.fetchall()

    @classmethod
    def _get_result(cls, cursor: CursorWrapper) -> Tuple:
        return cursor.fetchone()

    @classmethod
    def fetchall(cls, get_query: Callable, *args, **kwargs):
        sql, params = cls.get_raw_sql(get_query, *args, **kwargs)
        with connection.cursor() as cursor:
            cursor.execute(sql, params)
            return cls._get_many_result(cursor)

    @classmethod
    def fetchone(cls, get_query, *args, **kwargs):
        sql, params = cls.get_raw_sql(get_query, *args, **kwargs)
        with connection.cursor() as cursor:
            cursor.execute(sql, params)
            return cls._get_result(cursor)

    @classmethod
    def execute(cls, get_query, *args, **kwargs):
        sql, params = cls.get_raw_sql(get_query, *args, **kwargs)
        with connection.cursor() as cursor:
            cursor.execute(sql, params)


class OrderedDictQueryExecutor(QueryExecutor):
    @classmethod
    def __get_columns(cls, cursor: CursorWrapper) -> Columns:
        return [element[0] for element in cursor.description]

    @classmethod
    def _get_many_result(cls, cursor: CursorWrapper) -> ListOrderedDict:
        columns: list[str] = cls.__get_columns(cursor)
        return [OrderedDict(zip(columns, row)) for row in cursor.fetchall()]

    @classmethod
    def _get_result(cls, cursor: CursorWrapper) -> OrderedDict:
        columns: list[str] = cls.__get_columns(cursor)
        row = cursor.fetchone()
        return OrderedDict(zip(columns, row))


SAStatement = Union[ClauseElement, str, Tuple[str, Any]]


class DjangoSAExecutor:
    """
    Выполнение SQLAlchemy Core выражений через ``django.db.connection`` (PostgreSQL).

    По умолчанию выражение компилируется PostgreSQL-диалектом с
    ``literal_binds=True`` — все литералы инлайнятся прямо в SQL. Это
    повторяет поведение ``psycopg2.sql.Literal`` и упрощает миграцию с
    composable SQL: на стороне Django-курсора параметры не нужны.

    Для оптимизированных вызовов можно передать ``literal_binds=False`` —
    тогда возвращается пара ``(sql, params_dict)`` пригодная для
    ``cursor.execute(sql, params)``.
    """

    @staticmethod
    def compile(stmt: SAStatement, *, literal_binds: bool = True) -> Tuple[str, Any]:
        """
        Возвращает кортеж ``(sql_str, params)``.

        - ``stmt`` уже строка → ``(stmt, ())``.
        - ``stmt`` — кортеж ``(sql, params)`` → возвращается без изменений.
        - SQLAlchemy ``ClauseElement`` → компилируется PG-диалектом.
        """
        if isinstance(stmt, str):
            return stmt, ()
        if isinstance(stmt, tuple) and len(stmt) == 2:
            sql_text, params = stmt
            return sql_text, params if params is not None else ()
        compile_kwargs = {'literal_binds': True} if literal_binds else {}
        compiled = stmt.compile(
            dialect=postgresql.dialect(),
            compile_kwargs=compile_kwargs,
        )
        sql_str = str(compiled)
        if literal_binds:
            return sql_str, ()
        return sql_str, dict(compiled.params)

    @classmethod
    @contextmanager
    def cursor(cls, stmt: SAStatement, *, literal_binds: bool = True):
        """
        Контекст-менеджер: возвращает Django-курсор после выполнения запроса.
        Удобно, когда нужно прочитать ``description`` курсора.
        """
        sql_str, params = cls.compile(stmt, literal_binds=literal_binds)
        with connection.cursor() as cur:
            cur.execute(sql_str, params or None)
            yield cur

    @classmethod
    def execute(cls, stmt: SAStatement, *, literal_binds: bool = True) -> None:
        with cls.cursor(stmt, literal_binds=literal_binds):
            return None

    @classmethod
    def fetchall(
        cls, stmt: SAStatement, *, literal_binds: bool = True
    ) -> FetchResult:
        with cls.cursor(stmt, literal_binds=literal_binds) as cur:
            return cur.fetchall()

    @classmethod
    def fetchone(cls, stmt: SAStatement, *, literal_binds: bool = True) -> Tuple:
        with cls.cursor(stmt, literal_binds=literal_binds) as cur:
            return cur.fetchone()

    @classmethod
    def fetchall_with_columns(
        cls, stmt: SAStatement, *, literal_binds: bool = True
    ) -> Tuple[Columns, FetchResult]:
        """
        Возвращает ``(columns, rows)`` — имена колонок берутся из
        ``cursor.description``.
        """
        with cls.cursor(stmt, literal_binds=literal_binds) as cur:
            columns = [c[0] for c in (cur.description or [])]
            rows = cur.fetchall()
            return columns, rows
