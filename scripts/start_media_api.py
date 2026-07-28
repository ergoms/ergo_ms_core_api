"""
Запуск Media API: development — runserver, production — daphne (ASGI).
"""

import os
import subprocess
import sys
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
API_DIR = SCRIPT_DIR.parent
PROJECT_ROOT = API_DIR.parent.parent
MEDIA_SRC = PROJECT_ROOT / 'core' / 'media_api' / 'src'


def _read_env_var(name: str, default: str = '') -> str:
    value = os.environ.get(name)
    if value is not None and value != '':
        return value.strip()
    deployment = PROJECT_ROOT / 'core' / 'deployment'
    if str(deployment) not in sys.path:
        sys.path.insert(0, str(deployment))
    try:
        from env_file_loader import load_project_env  # noqa: WPS433
        return load_project_env(PROJECT_ROOT).get(name, default)
    except Exception:
        return default


def _build_env() -> dict:
    env = os.environ.copy()
    env['PYTHONIOENCODING'] = 'utf-8'
    env['PYTHONUTF8'] = '1'
    existing = env.get('PYTHONPATH', '')
    # API_DIR — для общего log_format (src.config.*) из media_server.
    paths = [str(MEDIA_SRC), str(API_DIR), str(PROJECT_ROOT)]
    if existing:
        paths.append(existing)
    env['PYTHONPATH'] = os.pathsep.join(paths)
    return env


def main() -> int:
    sys.path.insert(0, str(MEDIA_SRC))

    from media_server.deploy import get_deploy_type

    deploy_type = get_deploy_type()
    scripts_dir = PROJECT_ROOT / 'core' / 'deployment' / 'scripts'
    if str(scripts_dir) not in sys.path:
        sys.path.insert(0, str(scripts_dir))
    from deployment_env import is_nginx_enabled  # noqa: WPS433

    nginx_enabled = is_nginx_enabled()
    # MEDIA_API_BIND_PORT — порт процесса (8003). MEDIA_API_PORT — порт в публичных URL (80 за nginx).
    port = _read_env_var('MEDIA_API_BIND_PORT', '') or _read_env_var('MEDIA_API_PORT', '8003')
    if deploy_type == 'production' and port in ('80', '443'):
        port = _read_env_var('MEDIA_API_BIND_PORT', '8003')
    default_host = '127.0.0.1' if deploy_type == 'production' or nginx_enabled else '0.0.0.0'
    host = _read_env_var('MEDIA_API_BIND_HOST', default_host)
    env = _build_env()

    if deploy_type == 'production':
        from media_server.deploy import get_settings_module

        # Тот же формат, что у API (core/api/src/config/log_format.py).
        # В path нужен core/api, иначе `from src.config...` не резолвится.
        if str(API_DIR) not in sys.path:
            sys.path.insert(0, str(API_DIR))
        from src.config.log_format import DAPHNE_LOG_FMT

        env.setdefault('DJANGO_SETTINGS_MODULE', get_settings_module())
        cmd = [
            sys.executable, '-m', 'daphne',
            '-b', host,
            '-p', port,
            # NCSA access в null — единый HTTP-лог через RequestLoggingMiddleware.
            '--access-log', os.devnull,
            '--log-fmt', DAPHNE_LOG_FMT,
            'media_server.asgi:application',
        ]
        print(f'Media API (запуск как на сервере): daphne на {host}:{port}')
    else:
        cmd = [
            sys.executable, '-m', 'media_server.manage',
            'runserver', f'{host}:{port}',
        ]
        print(f'Media API (разработка): runserver на {host}:{port}')

    return subprocess.call(cmd, cwd=str(PROJECT_ROOT), env=env)


if __name__ == '__main__':
    raise SystemExit(main())
