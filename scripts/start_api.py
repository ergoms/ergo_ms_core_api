"""
Запуск API: development — dev/runserver (autoreload), production — daphne (ASGI).

Точка входа для systemd/NSSM и ergoms start-api.
Режим определяется ERGO_ENV (или API_DEPLOY_TYPE) в .env — см. src.config.deploy.
"""

import os
import subprocess
import sys
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
API_DIR = SCRIPT_DIR.parent
PROJECT_ROOT = API_DIR.parent.parent


def _ensure_sys_path() -> None:
    for path in (API_DIR, PROJECT_ROOT):
        entry = str(path)
        if entry not in sys.path:
            sys.path.insert(0, entry)


def _build_env() -> dict:
    env = os.environ.copy()
    env['PYTHONIOENCODING'] = 'utf-8'
    env['PYTHONUTF8'] = '1'
    path_entries = [str(PROJECT_ROOT), str(API_DIR)]
    existing = env.get('PYTHONPATH', '')
    merged = path_entries + ([existing] if existing else [])
    env['PYTHONPATH'] = os.pathsep.join(merged)
    return env


def main() -> int:
    _ensure_sys_path()

    from src.config.deploy import (
        build_dev_command,
        build_daphne_command,
        get_api_bind_host,
        get_api_bind_port,
        get_settings_module,
        is_production,
    )
    from src.core.utils.startup_timing import ENV_API_START_WALL, mark_start

    # Wall-clock старт до subprocess/autoreload — child наследует ERGO_API_START_WALL.
    mark_start(env_key=ENV_API_START_WALL)

    run_env = _build_env()
    run_env.setdefault('DJANGO_SETTINGS_MODULE', get_settings_module())

    host = get_api_bind_host()
    port = get_api_bind_port()

    if is_production():
        cmd = build_daphne_command(sys.executable)
        print(f'API (запуск как на сервере): daphne на {host}:{port}')
    else:
        cmd = build_dev_command(sys.executable)
        print(f'API (разработка): runserver на {host}:{port}')

    return subprocess.call(cmd, cwd=str(API_DIR), env=run_env)


if __name__ == '__main__':
    raise SystemExit(main())
