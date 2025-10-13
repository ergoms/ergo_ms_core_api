"""
Модуль для работы с переменными окружения.

Содержит функции для сбора и объединения .env файлов из всех источников.
"""

from .methods import collect_env_files_from_configs, collect_env_files_from_all_sources, get_env_sources

__all__ = [
    'collect_env_files_from_configs',
    'collect_env_files_from_all_sources',
    'get_env_sources'
]
