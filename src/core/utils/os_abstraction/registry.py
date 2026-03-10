"""
Регистрация и доступ к реализации OSAbstraction.
"""

import sys
from typing import TYPE_CHECKING

from src.core.utils.os_abstraction.implementations import LinuxImpl, WindowsImpl

if TYPE_CHECKING:
    from src.core.utils.os_abstraction.interface import OSAbstraction

_impl: 'OSAbstraction | None' = None


def _get_impl() -> 'OSAbstraction':
    if sys.platform == 'win32':
        return WindowsImpl()
    return LinuxImpl()


def get_os_abstraction() -> 'OSAbstraction':
    """Возвращает текущую реализацию ОС-абстракции."""
    global _impl
    if _impl is None:
        _impl = _get_impl()
    return _impl


def set_os_abstraction(impl: 'OSAbstraction | None') -> None:
    """
    Устанавливает реализацию (для тестов).
    Передайте None для сброса к автоопределению.
    """
    global _impl
    _impl = impl
