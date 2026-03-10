"""
Протокол для ОС-зависимых операций.
"""

from typing import Protocol


class OSAbstraction(Protocol):
    """Протокол для ОС-зависимых операций."""

    def is_windows(self) -> bool:
        """Возвращает True если целевая ОС — Windows."""
        ...

    def process_executable_names(self, base_name: str) -> tuple[str, ...]:
        """
        Возвращает возможные имена исполняемого файла процесса.

        Windows: (base_name, f"{base_name}.exe")
        Linux: (base_name,)
        """
        ...

    def server_process_name(self, base_name: str) -> str:
        """
        Возвращает имя процесса сервера для мониторинга.

        Windows: f"{base_name}.exe"
        Linux: base_name
        """
        ...

    def basename_from_path(self, path_str: str) -> str:
        """Извлекает имя файла из пути (поддержка / и \\.)"""
        ...

    def path_ends_with(self, path_str: str, component: str) -> bool:
        """Проверяет, заканчивается ли путь на component (учитывает / и \\.)"""
        ...
