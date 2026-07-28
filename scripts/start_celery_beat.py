"""
Скрипт запуска Celery beat без загрузки Django.

Запускает celery -A src beat. Django грузится только в процессе Celery.
"""

import argparse
import os
import sys
import time
from typing import List

import psutil

from _common import (
    API_DIR,
    ensure_caches,
    is_celery_process,
    run_celery_with_timing,
    setup_celery_script_logging,
)


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
    start_time = time.time()
    parser = argparse.ArgumentParser(description='Запуск Celery beat')
    parser.add_argument(
        '--verbose',
        action='store_true',
        help='Полные списки очередей и модулей при старте (или ERGO_CELERY_STARTUP_VERBOSE=true)',
    )
    parser.add_argument('--loglevel', default='info')
    opts, _unknown = parser.parse_known_args()

    if opts.verbose:
        os.environ['ERGO_CELERY_STARTUP_VERBOSE'] = 'true'

    log = setup_celery_script_logging('celery_beat')
    if find_celery_beat():
        log.info('Celery beat уже запущен')
        return 0

    log.info(
        'Подготовка Celery beat: подготавливаем кэш очередей и расписаний '
        '(warmup_celery при необходимости)...'
    )
    ensure_caches(verbose=opts.verbose)

    loglevel = opts.loglevel
    for arg in sys.argv[1:]:
        if arg.startswith('--loglevel='):
            loglevel = arg.split('=', 1)[1]
            break

    cmd: List[str] = [
        sys.executable, '-m', 'celery', '-A', 'src', 'beat',
        f'--loglevel={loglevel}',
    ]
    log.info('Запуск Celery beat (уровень логов=%s)...', loglevel)
    return run_celery_with_timing(
        cmd, str(API_DIR),
        ready_pattern='beat: Starting',
        service_name='Celery beat',
        start=start_time,
    )


if __name__ == '__main__':
    sys.exit(main())
