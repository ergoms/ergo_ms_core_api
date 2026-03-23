"""
Утилиты для изоляции тестов модулей.

Позволяет запускать тесты модуля с загрузкой только необходимых зависимостей,
а не всех модулей системы.
"""

from .module_deps import get_module_dependencies, get_isolated_apps

__all__ = ['get_module_dependencies', 'get_isolated_apps']
