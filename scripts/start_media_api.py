"""
Запуск Media API: development — dev/runserver (Daphne, autoreload), production — daphne.

Точка входа для systemd/NSSM и ergoms start-media.
Сценарий совпадает с start_api.py.
"""

import os
import subprocess
import sys
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
API_DIR = SCRIPT_DIR.parent
PROJECT_ROOT = API_DIR.parent.parent
MEDIA_SRC = PROJECT_ROOT / 'core' / 'media_api' / 'src'


def _ensure_sys_path() -> None:
    for path in (MEDIA_SRC, API_DIR, PROJECT_ROOT):
        entry = str(path)
        if entry not in sys.path:
            sys.path.insert(0, entry)


def _build_env() -> dict:
    env = os.environ.copy()
    env['PYTHONIOENCODING'] = 'utf-8'
    env['PYTHONUTF8'] = '1'
    env['PYTHONUNBUFFERED'] = '1'
    existing = env.get('PYTHONPATH', '')
    paths = [str(MEDIA_SRC), str(API_DIR), str(PROJECT_ROOT)]
    if existing:
        paths.append(existing)
    env['PYTHONPATH'] = os.pathsep.join(paths)
    return env


def main() -> int:
    _ensure_sys_path()

    from media_server.deploy import (
        build_dev_command,
        build_daphne_command,
        get_media_bind_host,
        get_media_bind_port,
        get_settings_module,
        is_production,
    )
    from src.core.utils.startup_timing import ENV_MEDIA_START_WALL, mark_start

    mark_start(env_key=ENV_MEDIA_START_WALL)

    run_env = _build_env()
    run_env.setdefault('DJANGO_SETTINGS_MODULE', get_settings_module())

    host = get_media_bind_host()
    port = get_media_bind_port()

    if is_production():
        cmd = build_daphne_command(sys.executable)
        print(f'Media API (запуск как на сервере): daphne на {host}:{port}')
    else:
        cmd = build_dev_command(sys.executable)
        print(f'Media API (разработка): runserver на {host}:{port}')

    return subprocess.call(cmd, cwd=str(PROJECT_ROOT), env=run_env)


if __name__ == '__main__':
    raise SystemExit(main())
