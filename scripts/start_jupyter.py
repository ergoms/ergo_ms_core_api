"""
Скрипт регистрации Django IPython kernel и запуска JupyterLab.

Устанавливает кастомный kernel 'ergo_django' с автоинициализацией Django ORM,
затем запускает JupyterLab с effective-настройками из jupyter_runtime.py.

Запуск: ergoms start-jupyter
"""

import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

from _common import API_DIR, PROJECT_ROOT, format_console

SCRIPT_DIR = Path(__file__).resolve().parent
KERNEL_NAME = 'ergo_django'
KERNEL_DISPLAY_NAME = 'Django Kernel (ERGO MS)'
KERNEL_LAUNCHER = SCRIPT_DIR / 'jupyter_django_kernel.py'
NOTEBOOKS_DIR = PROJECT_ROOT / 'notebooks'


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
        print(format_console('ok', f'Ядро Django установлено: {dest}'))
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

    cmd = [sys.executable, '-m', 'jupyterlab', *build_jupyter_server_argv(str(NOTEBOOKS_DIR))]

    print(format_console('info', 'Запуск JupyterLab...'))
    print(format_console('info', f'Каталог блокнотов: {NOTEBOOKS_DIR}'))
    _print_startup_info()

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
