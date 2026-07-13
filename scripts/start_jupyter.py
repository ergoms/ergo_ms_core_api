"""
Скрипт регистрации Django IPython kernel и запуска JupyterLab.

Устанавливает кастомный kernel 'ergo_django' с автоинициализацией Django ORM,
затем запускает JupyterLab с настройками из .env (API_JUPYTER_HOST, API_JUPYTER_PORT).

Запуск: ergoms start-jupyter
"""

import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

from _common import API_DIR, PROJECT_ROOT

SCRIPT_DIR = Path(__file__).resolve().parent
KERNEL_NAME = 'ergo_django'
KERNEL_DISPLAY_NAME = 'Django Kernel (ERGO MS)'
KERNEL_LAUNCHER = SCRIPT_DIR / 'jupyter_django_kernel.py'
NOTEBOOKS_DIR = PROJECT_ROOT / 'notebooks'


def _get_jupyter_settings():
    """Читает хост/порт Jupyter из .env без полной загрузки Django."""
    from src.config.env import env
    host = env.str('API_JUPYTER_HOST', default='localhost')
    port = env.str('API_JUPYTER_PORT', default='8002')
    return host, port


def _install_django_kernel():
    """Создаёт и устанавливает Django-aware IPython kernel spec."""
    python_exe = sys.executable.replace('\\', '/')
    launcher_path = str(KERNEL_LAUNCHER).replace('\\', '/')

    kernel_spec = {
        'argv': [python_exe, launcher_path, '-f', '{connection_file}'],
        'display_name': KERNEL_DISPLAY_NAME,
        'language': 'python',
        'env': {
            'ERGO_PROJECT_ROOT': str(PROJECT_ROOT).replace('\\', '/'),
        },
    }

    spec_dir = tempfile.mkdtemp(prefix='ergo_django_kernel_')
    try:
        kernel_json_path = Path(spec_dir) / 'kernel.json'
        with open(kernel_json_path, 'w', encoding='utf-8') as f:
            json.dump(kernel_spec, f, indent=2, ensure_ascii=False)

        from jupyter_client.kernelspec import KernelSpecManager
        ksm = KernelSpecManager()
        dest = ksm.install_kernel_spec(spec_dir, KERNEL_NAME, user=True)
        print(f'Ядро Django установлено: {dest}')
    finally:
        shutil.rmtree(spec_dir, ignore_errors=True)


def _ensure_venv_commonjs():
    """
    Создаёт package.json с type=commonjs в virtual_env/, чтобы Node.js
    не наследовал "type": "module" из корневого package.json проекта.
    Без этого JupyterLab's node-version-check.js падает с ReferenceError
    т.к. require() недоступен в ESM-контексте.
    """
    venv_pkg = PROJECT_ROOT / 'virtual_env' / 'package.json'
    if not venv_pkg.exists():
        venv_pkg.parent.mkdir(parents=True, exist_ok=True)
        venv_pkg.write_text('{"type": "commonjs"}\n', encoding='utf-8')


def _start_jupyterlab():
    """Запускает JupyterLab с настройками из .env."""
    host, port = _get_jupyter_settings()

    NOTEBOOKS_DIR.mkdir(parents=True, exist_ok=True)
    _ensure_venv_commonjs()

    cmd = [
        sys.executable, '-m', 'jupyterlab',
        '--ip', host,
        '--port', port,
        '--notebook-dir', str(NOTEBOOKS_DIR),
        '--ServerApp.allow_origin', '*',
        '--ServerApp.allow_remote_access', 'True',
        '--ServerApp.open_browser', 'False',
        '--ServerApp.token', '',
        '--ServerApp.password', '',
        '--ServerApp.websocket_ping_timeout', '30000',
    ]

    print(f'Запуск JupyterLab на {host}:{port}')
    print(f'Каталог блокнотов: {NOTEBOOKS_DIR}')
    print(f'Адрес: http://{host}:{port}/lab')

    env = os.environ.copy()
    existing_pythonpath = env.get('PYTHONPATH', '')
    env['PYTHONPATH'] = str(PROJECT_ROOT) + (os.pathsep + existing_pythonpath if existing_pythonpath else '')

    try:
        proc = subprocess.Popen(cmd, env=env)
        proc.wait()
        return proc.returncode or 0
    except KeyboardInterrupt:
        proc.terminate()
        proc.wait()
        return 0


def main():
    _install_django_kernel()
    return _start_jupyterlab()


if __name__ == '__main__':
    sys.exit(main())
