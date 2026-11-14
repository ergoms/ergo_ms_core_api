"""
Утилиты БД ядра.

Экспорт ленивый: настройки Django импортируют config_manager через этот пакет,
а main/base тянут pandas, sqlalchemy и sshtunnel (paramiko). Без ленивого
экспорта каждый старт API и Celery платил за них, даже если менеджер не нужен.
"""

from __future__ import annotations

from importlib import import_module
from typing import Any

_EXPORTS = {
    'QueryExecutor': '.main',
    'OrderedDictQueryExecutor': '.main',
    'DjangoSAExecutor': '.main',
    'DBManagerInterface': '.base',
    'SqlAlchemyManager': '.base',
    'BaseDatabaseConfigLoader': '.config_manager',
    'DatabaseConnectionTester': '.config_manager',
    'DjangoDatabaseConfigLoader': '.config_manager',
    'CeleryDatabaseConfigLoader': '.config_manager',
}

__all__ = list(_EXPORTS)


def __getattr__(name: str) -> Any:
    module_name = _EXPORTS.get(name)
    if module_name is None:
        raise AttributeError(f'module {__name__!r} has no attribute {name!r}')
    value = getattr(import_module(module_name, __name__), name)
    globals()[name] = value
    return value
