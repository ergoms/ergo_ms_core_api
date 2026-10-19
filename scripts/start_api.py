"""
Запуск API: development — dev/runserver (autoreload), production — daphne (ASGI).

Точка входа для systemd/NSSM и ergoms start-api.
Режим определяется ERGO_ENV (или API_DEPLOY_TYPE) в .env — см. src.config.deploy.
"""

import os
import signal
import subprocess
import sys
import time
from pathlib import Path

from _replace_process import replace_current_process

SCRIPT_DIR = Path(__file__).resolve().parent
API_DIR = SCRIPT_DIR.parent
PROJECT_ROOT = API_DIR.parent.parent
DEPLOYMENT_DIR = PROJECT_ROOT / 'core' / 'deployment'


def _ensure_sys_path() -> None:
    for path in (API_DIR, PROJECT_ROOT):
        entry = str(path)
        if entry not in sys.path:
            sys.path.insert(0, entry)
    deployment = str(DEPLOYMENT_DIR)
    if deployment not in sys.path:
        sys.path.insert(0, deployment)


def _ensure_api_secret() -> None:
    from security.ensure_secret import ensure_mode_secrets_for_process

    ensure_mode_secrets_for_process(PROJECT_ROOT)


def _build_env() -> dict:
    env = os.environ.copy()
    env['PYTHONIOENCODING'] = 'utf-8'
    env['PYTHONUTF8'] = '1'
    path_entries = [str(PROJECT_ROOT), str(API_DIR)]
    existing = env.get('PYTHONPATH', '')
    merged = path_entries + ([existing] if existing else [])
    env['PYTHONPATH'] = os.pathsep.join(merged)
    return env


def _stop_children(children: list[subprocess.Popen]) -> None:
    for proc in children:
        if proc.poll() is None:
            proc.terminate()
    for proc in children:
        if proc.poll() is not None:
            continue
        try:
            proc.wait(timeout=10)
        except subprocess.TimeoutExpired:
            proc.kill()


def _run_daphne_group(ports: list[int], run_env: dict) -> int:
    """Один родитель systemd, несколько Daphne. Падение любого гасит остальных."""
    from src.config.deploy import build_daphne_command, get_api_bind_host

    host = get_api_bind_host()
    children: list[subprocess.Popen] = []
    stop = False

    def _on_signal(signum, _frame):
        nonlocal stop
        stop = True
        _stop_children(children)

    signal.signal(signal.SIGTERM, _on_signal)
    signal.signal(signal.SIGINT, _on_signal)
    try:
        for port in ports:
            if stop:
                break
            cmd = build_daphne_command(sys.executable, port=port)
            children.append(subprocess.Popen(cmd, cwd=str(API_DIR), env=run_env))
            print(f'API (запуск как на сервере): daphne на {host}, порт {port}', flush=True)
    except Exception:
        _stop_children(children)
        raise

    exit_code = 0
    while not stop:
        for proc in children:
            code = proc.poll()
            if code is not None:
                exit_code = code
                stop = True
                break
        else:
            time.sleep(0.5)
            continue
        break
    _stop_children(children)
    return exit_code


def _production_ports() -> list[int]:
    from env_file_loader import load_project_env
    from api_processes import explicit_process_count, listen_ports, shared_process_state
    from src.config.deploy import get_api_bind_port

    merged = {**load_project_env(PROJECT_ROOT), **os.environ}
    raw = str(merged.get('API_PROCESSES') or 'auto')
    if not shared_process_state(merged) and explicit_process_count(raw) not in (None, 1):
        print(
            'API_PROCESSES больше одного требует общий кэш (redis или file) '
            'и channel layer (redis или postgres). Запускается один процесс.',
            file=sys.stderr,
        )
    return listen_ports(merged, base_port=int(get_api_bind_port()))


def main() -> int:
    _ensure_sys_path()
    from lifecycle.host_process_guard import refuse_unwanted_core_service
    from lifecycle.host_profile import SERVICE_API

    refused = refuse_unwanted_core_service(
        SERVICE_API,
        message_key='host_refuses_core_api',
        project_root=PROJECT_ROOT,
    )
    if refused:
        return refused

    _ensure_api_secret()

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
    # Фильтр INSTALLED_APPS в MODULE_RUNTIME=microservice (исключает MICROSERVICE_MODULES).
    run_env.setdefault('ERGO_PROCESS_ROLE', 'api')

    host = get_api_bind_host()
    port = get_api_bind_port()

    if is_production():
        ports = _production_ports()
        if len(ports) > 1:
            return _run_daphne_group(ports, run_env)
        cmd = build_daphne_command(sys.executable, port=ports[0])
        print(f'API (запуск как на сервере): daphne на {host}, порт {ports[0]}')
    else:
        cmd = build_dev_command(sys.executable)
        print(f'API (разработка): runserver на {host}, порт {port}')

    return replace_current_process(cmd, cwd=str(API_DIR), env=run_env)


if __name__ == '__main__':
    raise SystemExit(main())
