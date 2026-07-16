"""
Скрипт запуска Celery worker.

Читает celery_workers.yaml и кэш очередей, при пустом кэше вызывает warmup_caches,
затем запускает celery -A src worker. Django грузится только в Celery-процессе.
"""

import argparse
import os
import subprocess
import sys
import time
from typing import Any, Dict, List, Optional

import psutil
import yaml

from _common import (
    API_DIR,
    PROJECT_ROOT,
    WORKERS_CONFIG,
    ensure_caches,
    is_celery_process,
    read_queues_cache,
    run_celery_with_timing,
)
from src.core.utils.celery.startup_format import format_queues_display


def load_workers_config() -> Dict[str, Any]:
    """Загружает celery_workers.yaml без Django."""
    if not WORKERS_CONFIG.exists():
        return {}
    try:
        with open(WORKERS_CONFIG, 'r', encoding='utf-8') as f:
            return yaml.safe_load(f) or {}
    except Exception:
        return {}


def find_celery_worker(queues: Optional[str] = None, hostname: Optional[str] = None) -> bool:
    """Проверяет, запущен ли worker с указанными параметрами."""
    for proc in psutil.process_iter(['cmdline']):
        try:
            cmdline = proc.info.get('cmdline') or []
            if not is_celery_process(cmdline):
                continue
            cmdline_lower = [str(p).lower() for p in cmdline]
            if 'worker' not in cmdline_lower:
                continue
            cmdline_str = ' '.join(cmdline)
            if hostname and (f'--hostname={hostname}' in cmdline_str or f'-n {hostname}' in cmdline_str):
                return True
            if queues:
                for i, arg in enumerate(cmdline):
                    if arg == '-Q' and i + 1 < len(cmdline):
                        worker_queues = set(cmdline[i + 1].lower().split(','))
                        requested = set(q.strip().lower() for q in queues.split(','))
                        if requested.issubset(worker_queues):
                            return True
                        break
            elif not hostname:
                return True
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            continue
    return False


def resolve_queues(queues_config: Any, all_queues: List[str]) -> Optional[List[str]]:
    """
    Преобразует конфиг очередей в список.
    Возвращает [] для режима 'all' при пустом all_queues (celery без -Q).
    """
    if queues_config == 'all' or queues_config is None:
        if not all_queues:
            return []
        names = {'default'}
        names.update(all_queues)
        return sorted(names)
    if isinstance(queues_config, list):
        return queues_config
    if isinstance(queues_config, str):
        return [q.strip() for q in queues_config.split(',')]
    return []


def build_cmd(
    queues: Optional[List[str]],
    hostname: str,
    loglevel: str = 'info',
    concurrency: Optional[int] = None,
    pool: str = 'threads',
) -> List[str]:
    """Формирует команду celery worker. queues=None или [] — без -Q (все очереди)."""
    effective_pool = (pool or 'threads').strip().lower()
    cmd = [
        sys.executable, '-m', 'celery', '-A', 'src', 'worker',
        f'--hostname={hostname}', f'--loglevel={loglevel}',
        f'--pool={effective_pool}', '-E',
    ]
    if queues:
        cmd.extend(['-Q', ','.join(queues)])
    if concurrency:
        cmd.append(f'--concurrency={concurrency}')
    return cmd


def main() -> int:
    start_time = time.perf_counter()
    parser = argparse.ArgumentParser(description='Запуск Celery worker')
    parser.add_argument('--worker', type=str, default=None)
    parser.add_argument('--list-workers', action='store_true')
    parser.add_argument('--queues', type=str, default=None)
    parser.add_argument('--hostname', type=str, default=None)
    parser.add_argument('--concurrency', type=int, default=None)
    parser.add_argument('--pool', type=str, default=None, help='пул: threads | prefork | solo')
    parser.add_argument('--loglevel', default='info')
    parser.add_argument(
        '--verbose',
        action='store_true',
        help='Полные списки очередей и модулей при старте (или ERGO_CELERY_STARTUP_VERBOSE=true)',
    )
    opts = parser.parse_args()

    if opts.verbose:
        os.environ['ERGO_CELERY_STARTUP_VERBOSE'] = 'true'

    config = load_workers_config()
    workers_config = config.get('workers', {})
    defaults = config.get('defaults', {})
    default_pool = defaults.get('pool', 'threads')
    print('Подготовка Celery worker: читаем кэш очередей (warmup_celery при необходимости)...')
    all_queues = ensure_caches(verbose=opts.verbose)

    if opts.list_workers:
        if not workers_config:
            print(f'В {WORKERS_CONFIG} нет worker\'ов')
            return 0
        print('\nWorker\'ы:')
        for name, w in workers_config.items():
            q = w.get('queues', [])
            if q == 'all':
                qs = 'все'
            elif isinstance(q, str):
                qs = q
            elif isinstance(q, list):
                qs = ', '.join(q) if q else 'нет'
            else:
                qs = 'нет'
            pool = w.get('pool') or default_pool
            print(f"  {name}: {w.get('description', '')} очереди={qs} пул={pool}")
        return 0

    worker_name = opts.worker
    queues_opt = opts.queues
    hostname_opt = opts.hostname
    loglevel_opt = opts.loglevel or defaults.get('loglevel', 'info')
    concurrency_opt = opts.concurrency
    pool_opt = opts.pool or default_pool
    pool = pool_opt

    if worker_name:
        if worker_name not in workers_config:
            print(f"Worker '{worker_name}' не найден. Доступные: {', '.join(workers_config.keys())}")
            return 1
        w = workers_config[worker_name]
        queues = resolve_queues(w.get('queues'), all_queues)
        hostname = w.get('hostname', f'worker@{worker_name}')
        concurrency = w.get('concurrency') or concurrency_opt
        loglevel = w.get('loglevel') or loglevel_opt
        pool = w.get('pool') or pool_opt
        print(f"\nЗапуск worker'а '{worker_name}': {w.get('description', '')}")
        queues_display = format_queues_display(queues, all_queues, verbose=opts.verbose)
        print(
            f"  Режим: worker из конфигурации (--worker), hostname={hostname}, "
            f"очереди={queues_display}, "
            f"параллелизм={concurrency or 'по умолчанию'}, пул={pool}"
        )
    elif queues_opt or hostname_opt:
        if queues_opt:
            queue_list = [q.strip() for q in queues_opt.split(',')]
            if all_queues:
                invalid = set(queue_list) - set(all_queues) - {'default'}
                if invalid:
                    from src.core.utils.celery.startup_format import format_name_list

                    available = format_name_list(all_queues, verbose=opts.verbose)
                    print(f'Неизвестные очереди: {invalid}. Доступные: {available}')
                    return 1
            queues = queue_list
        else:
            queues = resolve_queues(None, all_queues)
        hostname = hostname_opt or f"worker@{'_'.join(queues or ['all'])[:50]}"
        concurrency = concurrency_opt
        loglevel = loglevel_opt
        pool = pool_opt
        print('\nЗапуск Celery worker')
        queues_display = format_queues_display(queues, all_queues, verbose=opts.verbose)
        print(
            f"  Режим: worker из аргументов командной строки, hostname={hostname}, "
            f"очереди={queues_display}, "
            f"параллелизм={concurrency or 'по умолчанию'}, пул={pool}"
        )
    elif workers_config:
        procs = []
        print('\nЗапуск Celery worker\'ов из celery_workers.yaml (несколько процессов)...')
        for name, w in workers_config.items():
            queues = resolve_queues(w.get('queues'), all_queues)
            hostname = w.get('hostname', f'worker@{name}')
            if find_celery_worker(hostname=hostname):
                print(f"  {hostname} уже запущен, пропуск")
                continue
            queues_display = format_queues_display(queues, all_queues, verbose=opts.verbose)
            worker_pool = w.get('pool') or default_pool
            cmd = build_cmd(
                queues,
                hostname,
                w.get('loglevel', defaults.get('loglevel', 'info')),
                w.get('concurrency'),
                pool=worker_pool,
            )
            print(
                f"  Запуск '{name}' ({hostname}) -> очереди={queues_display}, "
                f"параллелизм={w.get('concurrency') or 'по умолчанию'}, пул={worker_pool}"
            )
            env = os.environ.copy()
            env.setdefault('PYTHONPATH', '')
            env['PYTHONPATH'] = str(PROJECT_ROOT) + (os.pathsep + env['PYTHONPATH'] if env['PYTHONPATH'] else '')
            # Не перенаправляем stdout в PIPE без чтения — иначе воркер зависает
            # при заполнении буфера во время загрузки Django/Celery.
            proc = subprocess.Popen(
                cmd, cwd=str(API_DIR), start_new_session=True, env=env,
            )
            procs.append(proc)
            time.sleep(0.3)
        if not procs:
            print('Нет worker\'ов для запуска')
            return 0
        print('\nДля остановки нажмите Ctrl+C...')
        try:
            while any(p.poll() is None for p in procs):
                time.sleep(1)
        except KeyboardInterrupt:
            for p in procs:
                if p.poll() is None:
                    p.terminate()
            time.sleep(2)
            for p in procs:
                if p.poll() is None:
                    p.kill()
        return 0
    else:
        queues = resolve_queues(None, all_queues)
        hostname = f"worker@{'_'.join(queues or ['all'])[:50]}"
        concurrency = concurrency_opt
        loglevel = loglevel_opt
        pool = pool_opt
        print('Файл celery_workers.yaml не найден. Запуск одного worker\'а со всеми очередями (без -Q, если кэш пуст).')

    queues_display = format_queues_display(queues, all_queues, verbose=opts.verbose)
    if find_celery_worker(hostname=hostname):
        print(f'Worker {hostname} уже запущен')
        return 0

    print(f'  Запуск {hostname}, очереди: {queues_display}, пул={pool}')
    cmd = build_cmd(queues, hostname, loglevel, concurrency, pool=pool)
    return run_celery_with_timing(
        cmd, str(API_DIR),
        ready_pattern='Connected to',
        service_name='Celery worker',
        start=start_time,
    )


if __name__ == '__main__':
    sys.exit(main())
