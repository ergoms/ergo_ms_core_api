"""
Версия системы ERGO MS.

Реэкспорт из core.shared — единый источник для Django API.
"""

from core.shared.system_version import (
    SYSTEM_VERSION,
    SYSTEM_VERSION_DISPLAY,
    get_system_version,
    get_system_version_display,
)

__all__ = [
    'SYSTEM_VERSION',
    'SYSTEM_VERSION_DISPLAY',
    'get_system_version',
    'get_system_version_display',
]
