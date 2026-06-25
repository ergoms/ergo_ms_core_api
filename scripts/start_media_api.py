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
    env_path = PROJECT_ROOT / '.env'
    if not env_path.is_file():
        return default
    try:
        for line in env_path.read_text(encoding='utf-8').splitlines():
            line = line.strip()
            if not line or line.startswith('#') or '=' not in line:
                continue
            key, _, raw = line.partition('=')
            if key.strip() == name:
                return raw.strip().strip('"').strip("'")
    except OSError:
        pass
    return default


def _build_env() -> dict:
    env = os.environ.copy()
    env['PYTHONIOENCODING'] = 'utf-8'
    env['PYTHONUTF8'] = '1'
    existing = env.get('PYTHONPATH', '')
    env['PYTHONPATH'] = str(MEDIA_SRC) + (os.pathsep + existing if existing else '')
    return env


def main() -> int:
    sys.path.insert(0, str(MEDIA_SRC))

    deploy_type = _read_env_var('MEDIA_API_DEPLOY_TYPE', 'development').lower()
    port = _read_env_var('MEDIA_API_PORT', '8003')
    default_host = '127.0.0.1' if deploy_type == 'production' else '0.0.0.0'
    host = _read_env_var('MEDIA_API_BIND_HOST', default_host)
    env = _build_env()

    if deploy_type == 'production':
        from media_server.deploy import get_settings_module

        env.setdefault('DJANGO_SETTINGS_MODULE', get_settings_module())
        cmd = [
            sys.executable, '-m', 'daphne',
            '-b', host,
            '-p', port,
            'media_server.asgi:application',
        ]
        print(f'Media API [production]: daphne on {host}:{port}')
    else:
        cmd = [
            sys.executable, '-m', 'media_server.manage',
            'runserver', f'{host}:{port}',
        ]
        print(f'Media API [development]: runserver on {host}:{port}')

    return subprocess.call(cmd, cwd=str(PROJECT_ROOT), env=env)


if __name__ == '__main__':
    raise SystemExit(main())
