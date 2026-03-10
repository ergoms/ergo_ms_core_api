"""
Скрипт запуска Celery beat без загрузки Django.

Запускает celery -A src beat. Django грузится только в процессе Celery.
"""

import sys
import time
from typing import List

import psutil

from _common import API_DIR, ensure_caches, is_celery_process, run_celery_with_timing


def find_celery_beat() -> bool:
    """Проверяет, запущен ли Celery beat."""
    for proc in psutil.process_iter(['cmdline']):
        try:
            cmdline = proc.info.get('cmdline') or []
            if not is_celery_process(cmdline):
                continue
            cmdline_lower = [str(p).lower() for p in cmdline]
            if 'beat' in cmdline_lower:
                return True
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            continue
    return False


def main() -> int:
    start_time = time.perf_counter()
    if find_celery_beat():
        print('Celery beat is already running')
        return 0

    print('Celery Beat bootstrap: подготавливаем кэш очередей/расписаний (warmup_celery при необходимости)...')
    ensure_caches()

    loglevel = 'info'
    for arg in sys.argv[1:]:
        if arg.startswith('--loglevel='):
            loglevel = arg.split('=', 1)[1]
            break

    cmd: List[str] = [
        sys.executable, '-m', 'celery', '-A', 'src', 'beat',
        f'--loglevel={loglevel}',
    ]
    print(f'Starting Celery beat (loglevel={loglevel})...')
    return run_celery_with_timing(
        cmd, str(API_DIR),
        ready_pattern='beat: Starting',
        service_name='Celery Beat',
        start=start_time,
    )


if __name__ == '__main__':
    sys.exit(main())
