"""Чтение значений из корневого .env до django.setup."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Optional


def find_project_root(start: Path | None = None) -> Path | None:
    current = (start or Path(__file__)).resolve()
    if current.is_file():
        current = current.parent
    for parent in [current, *current.parents]:
        if (parent / 'modules').is_dir() and (parent / 'core').is_dir():
            return parent
    return None


def read_env_value(key: str, *, root: Path | None = None, start: Path | None = None) -> Optional[str]:
    """Читает одну переменную из корневого .env без django.setup."""
    project_root = root or find_project_root(start)
    if project_root is None:
        return None
    env_path = project_root / '.env'
    if not env_path.is_file():
        return None
    try:
        for line in env_path.read_text(encoding='utf-8').splitlines():
            line = line.strip()
            if not line or line.startswith('#') or '=' not in line:
                continue
            env_key, _, value = line.partition('=')
            if env_key.strip() == key:
                return value.strip().strip('"').strip("'")
    except OSError:
        return None
    return None


def bootstrap_api_secret_key(*, root: Path | None = None, start: Path | None = None) -> None:
    """Подгружает API_SECRET_KEY из .env в os.environ (для подписи кэша до django.setup)."""
    if os.environ.get('API_SECRET_KEY'):
        return
    value = read_env_value('API_SECRET_KEY', root=root, start=start)
    if value:
        os.environ['API_SECRET_KEY'] = value
