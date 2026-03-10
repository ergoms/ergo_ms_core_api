"""
Слой абстракции для ОС-зависимой логики (Windows/Linux).

Позволяет тестировать код с подменой реализации через set_os_abstraction().
"""

from src.core.utils.os_abstraction.registry import (
    get_os_abstraction,
    set_os_abstraction,
)

__all__ = [
    'get_os_abstraction',
    'set_os_abstraction',
]
