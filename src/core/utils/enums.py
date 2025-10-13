"""
Файл с определениями перечислений (enums) для приложения.

Содержит определения различных перечислимых типов, используемых в приложении:
- LogLevel: уровни логирования (INFO, WARNING, ERROR, NONE)

Эти перечисления используются для типизации и стандартизации значений в различных частях приложения.
"""

from enum import Enum

class LogLevel(Enum):
    INFO = 'info'
    WARNING = 'warning'
    ERROR = 'error'
    NONE = 'none'