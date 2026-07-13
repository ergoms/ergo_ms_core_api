"""
Пути логов и чтение ERGO_LOG_* из .env без Django settings.
"""

from __future__ import annotations

import sys
from functools import lru_cache
from pathlib import Path


def _read_env_file(name: str, env_file: Path, default: str = '') -> str:
    import os

    value = os.environ.get(name)
    if value is not None and str(value).strip() != '':
        return str(value).strip()
    if not env_file.is_file():
        return default
    try:
        for line in env_file.read_text(encoding='utf-8').splitlines():
            line = line.strip()
            if not line or line.startswith('#') or '=' not in line:
                continue
            key, _, raw = line.partition('=')
            if key.strip() == name:
                return raw.strip().strip('"').strip("'")
    except OSError:
        pass
    return default


def project_root_from_system_dir(system_dir: Path) -> Path:
    return system_dir


def resolve_logs_root(system_dir: Path) -> Path:
    return _load_log_env().resolve_logs_dir(system_dir)


def read_bool_env(name: str, env_file: Path, default: bool = True) -> bool:
    return _load_log_env().read_bool(name, default, env_file.parent)


def read_log_level_env(name: str, env_file: Path, default: str) -> str:
    raw = _read_env_file(name, env_file, default)
    return raw.upper() if raw else default.upper()


def read_int_env(name: str, env_file: Path, default: int) -> int:
    raw = _read_env_file(name, env_file, '')
    if not raw:
        return default
    try:
        return int(raw)
    except ValueError:
        return default


@lru_cache(maxsize=1)
def _load_log_env():
    scripts = Path(__file__).resolve().parents[4] / 'core' / 'deployment' / 'scripts'
    if str(scripts) not in sys.path:
        sys.path.insert(0, str(scripts))
    import log_env

    return log_env


def log_basename(key: str, system_dir: Path) -> str:
    return _load_log_env().log_basename(key, system_dir)


def rotation_settings(system_dir: Path) -> dict[str, int]:
    return _load_log_env().rotation_settings(system_dir)


def service_levels(service: str, system_dir: Path) -> tuple[str, str, bool]:
    return _load_log_env().service_levels(service, system_dir)


def file_level_for_key(key: str, system_dir: Path, service_prefix: str | None = None) -> str:
    return _load_log_env().file_level_for_key(key, system_dir, service_prefix)


def resolve_logging_service(argv: list[str] | None = None) -> str:
    return _load_log_env().resolve_logging_service(argv)
