"""Утилиты преобразования путей файловой системы в Python dot-notation."""


def convert_path_to_dot_notation(path) -> str:
    """Путь Path/str → dot-notation для Python-модуля (напр. core/api → core.api)."""
    path_str = str(path)
    return path_str.replace('/', '.').replace('\\', '.').strip('.')
