"""
Пути проекта без зависимостей от Django settings и env.

Используется env.py до загрузки .env, чтобы избежать циклических импортов.
"""

from pathlib import Path

_CONFIG_DIR = Path(__file__).resolve().parent
_SRC_DIR = _CONFIG_DIR.parent
BASE_DIR = _SRC_DIR
API_DIR = _SRC_DIR.parent
CORE_DIR = API_DIR.parent
SYSTEM_DIR = CORE_DIR.parent

ENV_FILE_PATH = SYSTEM_DIR / '.env'
MODULES_DIR = SYSTEM_DIR / 'modules'
VIRTUAL_ENV_DIR = SYSTEM_DIR / 'virtual_env'

from src.config.log_paths import resolve_logs_root  # noqa: E402

LOGS_ROOT = resolve_logs_root(SYSTEM_DIR)
