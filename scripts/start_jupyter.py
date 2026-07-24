"""
Скрипт регистрации Django IPython kernel и запуска JupyterLab.

Устанавливает кастомный kernel 'ergo_django' с автоинициализацией Django ORM,
затем запускает JupyterLab с effective-настройками из jupyter_runtime.py.

Запуск: ergoms start-jupyter
"""

import json
import os
import subprocess
import sys
from pathlib import Path

from _common import API_DIR, PROJECT_ROOT, format_console

_DEPLOYMENT_DIR = PROJECT_ROOT / 'core' / 'deployment'
if str(_DEPLOYMENT_DIR) not in sys.path:
    sys.path.insert(0, str(_DEPLOYMENT_DIR))

from project_layout import (  # noqa: E402
    ensure_dir,
    jupyter_dir,
    jupyter_kernels_dir,
)

SCRIPT_DIR = Path(__file__).resolve().parent
KERNEL_NAME = 'ergo_django'
KERNEL_DISPLAY_NAME = 'Django Kernel (ERGO MS)'
KERNEL_LAUNCHER = SCRIPT_DIR / 'jupyter_django_kernel.py'
NOTEBOOKS_DIR = PROJECT_ROOT / 'notebooks'


def _install_django_kernel():
    """Создаёт Django-aware IPython kernel spec в virtual_env/jupyter/kernels."""
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

    dest = ensure_dir(jupyter_kernels_dir(PROJECT_ROOT) / KERNEL_NAME)
    kernel_json_path = dest / 'kernel.json'
    kernel_json_path.write_text(
        json.dumps(kernel_spec, indent=2, ensure_ascii=False) + '\n',
        encoding='utf-8',
    )
    print(format_console('ok', f'Ядро Django установлено: {dest}'))


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


def _print_startup_info():
    from src.config.jupyter_runtime import (
        effective_jupyter_access_mode,
        effective_jupyter_bind_host,
        effective_jupyter_bind_port,
        effective_jupyter_security,
        jupyter_public_lab_url,
    )

    mode = effective_jupyter_access_mode()
    security = effective_jupyter_security()
    bind_host = effective_jupyter_bind_host()
    bind_port = effective_jupyter_bind_port()
    lab_url = jupyter_public_lab_url()

    print(format_console('info', f'Режим доступа Jupyter: {mode}'))
    print(format_console('info', f'Bind: {bind_host}:{bind_port}'))
    print(format_console('info', f'Публичный адрес: {lab_url}'))

    if security['require_token']:
        print(format_console(
            'info',
            'Токен задан в API_JUPYTER_TOKEN — откройте lab с параметром ?token=...',
        ))
    if security['require_admin_gate']:
        print(format_console(
            'info',
            'За nginx доступ только для глобального администратора (сессия SPA + токен Jupyter)',
        ))


def _start_jupyterlab():
    """Запускает JupyterLab с effective-настройками."""
    from src.config.jupyter_runtime import build_jupyter_server_argv, validate_jupyter_startup

    startup_error = validate_jupyter_startup()
    if startup_error:
        print(format_console('error', startup_error), file=sys.stderr)
        return 1

    NOTEBOOKS_DIR.mkdir(parents=True, exist_ok=True)
    _ensure_venv_commonjs()

    data_dir = ensure_dir(jupyter_dir(PROJECT_ROOT))
    cmd = [sys.executable, '-m', 'jupyterlab', *build_jupyter_server_argv(str(NOTEBOOKS_DIR))]

    print(format_console('info', 'Запуск JupyterLab...'))
    print(format_console('info', f'Каталог блокнотов: {NOTEBOOKS_DIR}'))
    _print_startup_info()

    env = os.environ.copy()
    existing_pythonpath = env.get('PYTHONPATH', '')
    env['PYTHONPATH'] = str(PROJECT_ROOT) + (os.pathsep + existing_pythonpath if existing_pythonpath else '')
    env['JUPYTER_DATA_DIR'] = str(data_dir)
    env['JUPYTER_PATH'] = str(data_dir)

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
