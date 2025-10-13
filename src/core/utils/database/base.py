import logging
import abc
import time

from collections import OrderedDict
from typing import Any

import psycopg2
import pandas as pd

import sqlalchemy as sa
from sqlalchemy.sql import text
from sqlalchemy.exc import OperationalError, SQLAlchemyError

from src.core.utils.database.dbconfig import DBConfig


logger = logging.getLogger(__name__)

MAX_RETRIES = 3
# в секундах
RETRY_DELAY = 1

class DBManagerInterface(abc.ABC):
    def _get_query(self, get_query, *args, **kwargs):
        params = tuple()
        sql = ""
        try:
            sql, params = get_query(*args, **kwargs)
        except ValueError:
            sql = get_query(*args, **kwargs)
        logger.debug(params)
        return sql, params

    @abc.abstractmethod
    def fetchall(self, get_query, *args, **kwargs):
        pass

    @abc.abstractmethod
    def fetchone(self, get_query, *args, **kwargs):
        pass

    @abc.abstractmethod
    def execute(self, get_query, *args, **kwargs):
        pass


class DataBaseManager(DBManagerInterface):
    def __init__(self, config: DBConfig) -> None:
        self.connection = psycopg2.connect(config.POSTGRESQL_URL)

    def _get_rows(self, rows):
        if not rows:
            return []
        return rows

    def _get_columns(self, description):
        return [column[0] for column in description]

    def fetchall(self, sql: str, params: tuple):
        with self.connection.cursor() as cursor:
            cursor.execute(sql, params)
            return self.all(cursor)

    def fetchone(self, sql: str, params: tuple):
        with self.connection.cursor() as cursor:
            cursor.execute(sql, params)
            return self.one(cursor)

    def execute(self, sql: str, params: tuple):
        with self.connection.cursor() as cursor:
            cursor.execute(sql, params)
            return None

    def one(self, cursor):
        rows = cursor.fetchone()
        if rows:
            columns = self._get_columns(cursor.description)
            return OrderedDict(zip(columns, rows))
        else:
            return OrderedDict()

    def all(self, cursor):
        rows = cursor.fetchall()
        if rows:
            columns = self._get_columns(cursor.description)
            return [OrderedDict(zip(columns, row)) for row in rows]
        else:
            return []

    def close(self):
        self.connection.commit()
        self.connection.close()


class SqlAlchemyManager(DBManagerInterface):
    def __init__(self, config: DBConfig) -> None:
        self.config = config
        self.engine = self._create_engine()

    def _create_engine(self) -> sa.Engine:
        return sa.create_engine(
            self.config.SQLALCHEMY_URL,
            pool_pre_ping=True,
            pool_recycle=3600,
            connect_args={
                "connect_timeout": 10,
                "keepalives": 1,
                "keepalives_idle": 30,
                "keepalives_interval": 10,
                "keepalives_count": 5
            }
        )

    def _execute_with_retry(self, operation: callable, *args: Any, **kwargs: Any) -> Any:
        last_error = None
        for attempt in range(MAX_RETRIES):
            try:
                return operation(*args, **kwargs)
            except (OperationalError, SQLAlchemyError) as e:
                last_error = e
                if attempt < MAX_RETRIES - 1:
                    logger.warning(f"Database operation failed (attempt {attempt + 1}/{MAX_RETRIES}): {str(e)}")
                    time.sleep(RETRY_DELAY)
                    # Пересоздаем engine при ошибке подключения
                    self.engine = self._create_engine()
        raise last_error

    def fetchall(self, get_query, *args, **kwargs) -> pd.DataFrame:
        sql, params = self._get_query(get_query, *args, **kwargs)
        
        def _fetchall():
            return pd.read_sql_query(sql, con=self.engine, params=params)
        
        return self._execute_with_retry(_fetchall)

    def fetchone(self, get_query, *args, **kwargs):
        return 0

    def execute(self, get_query, *args, **kwargs):
        sql, params = self._get_query(get_query, *args, **kwargs)
        def _execute():
            with self.engine.begin() as conn:
                conn.execute(text(sql), params)
        return self._execute_with_retry(_execute)

    def close(self):
        return 0

    def to_sql(self, df: pd.DataFrame, table_name: str, chunksize: int = 10000):
        columns = df.select_dtypes(include=["object"]).columns.tolist()
        dtype = {col_name: sa.types.VARCHAR(250) for col_name in columns}
        df.to_sql(
            name=table_name,
            con=self.engine,
            if_exists="append",
            index=False,
            dtype=dtype,
            chunksize=chunksize
        )