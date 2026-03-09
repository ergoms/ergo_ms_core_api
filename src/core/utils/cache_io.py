"""
Утилиты для бинарной записи/чтения кэша (pickle).
Файлы .bin не читаемы в текстовом виде — снижает риск утечки .env и прочих чувствительных данных.
"""

import logging
import pickle
from pathlib import Path
from typing import Any, Optional

logger = logging.getLogger('utils.cache')

_PROTOCOL = 4


def write_bin_cache(path: Path, data: Any) -> bool:
    """Записывает данные в бинарный кэш. Возвращает True при успехе."""
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, 'wb') as f:
            pickle.dump(data, f, protocol=_PROTOCOL)
        return True
    except OSError as e:
        logger.warning('Не удалось записать кэш %s: %s', path.name, e)
        return False


def read_bin_cache(path: Path) -> Optional[Any]:
    """Читает данные из бинарного кэша. Возвращает None при ошибке."""
    if not path.exists() or path.stat().st_size == 0:
        return None
    try:
        with open(path, 'rb') as f:
            return pickle.load(f)
    except (pickle.PickleError, OSError, EOFError):
        return None
