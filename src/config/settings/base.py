"""
Файл содержащий базовую конфигурацию для Django-приложения.
Он включает настройки базового каталога проекта.
"""

from pathlib import Path

"""
Определяет базовый каталог проекта.

BASE_DIR используется для построения путей к различным ресурсам проекта, таким как шаблоны, статические файлы и т.д.
"""
# Получаем путь к корневой директории проекта (ergo_ms/api/src)
BASE_DIR = Path(__file__).resolve().parent.parent.parent

# Получаем путь к директории api (ergo_ms/api)
API_DIR = Path(__file__).resolve().parent.parent.parent.parent

# Получаем путь к директории системы (ergo_ms/)
SYSTEM_DIR = Path(__file__).resolve().parent.parent.parent.parent.parent.parent