"""
Общие константы и утилиты для скриптов запуска Celery (worker, beat, warmup).

Все скрипты в scripts/ импортируют пути и функции отсюда,
чтобы избежать дублирования логики чтения кэша и fingerprint.
"""

import pickle
import os
import subprocess
import sys
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

SCRIPT_DIR = Path(__file__).resolve().parent
API_DIR = SCRIPT_DIR.parent
PROJECT_ROOT = API_DIR.parent.parent
if str(API_DIR) not in sys.path:
    sys.path.insert(0, str(API_DIR))
MODULES_DIR = PROJECT_ROOT / 'modules'
WORKERS_CONFIG = PROJECT_ROOT / 'celery_workers.yaml'
CACHE_DIR = PROJECT_ROOT / 'virtual_env' / 'cache'
CACHE_FILE = CACHE_DIR / 'celery_queues.bin'
ROUTES_QUEUES_CACHE_FILE = CACHE_DIR / 'celery_routes_queues.bin'
WARMUP_LOCK = CACHE_DIR / 'warmup.lock'
LOCK_MAX_AGE = 120


def _pid_exists(pid: int) -> bool:
    """Кроссплатформенная проверка существования процесса."""
    try:
        os.kill(pid, 0)
        return True
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    except OSError:
        return False


def is_celery_process(cmdline: list) -> bool:
    """Проверяет, что cmdline — реальный процесс Celery, а не grep/cat и т.п."""
    if len(cmdline) < 2:
        return False
    first = str(cmdline[0]).lower()
    return 'python' in first or first.endswith(('celery', 'celery.exe'))


def get_modules_config_mtime() -> float:
    """Max mtime по celery_config.py / celery_beat_config.py модулей."""
    from src.core.utils.cache_fingerprint import get_modules_config_max_mtime
    return get_modules_config_max_mtime(MODULES_DIR)


def get_fingerprint() -> Dict[str, float]:
    """Fingerprint для routes/queues кэша (celery_routes_queues.bin)."""
    from src.core.utils.cache_fingerprint import get_celery_config_fingerprint
    return get_celery_config_fingerprint(PROJECT_ROOT, MODULES_DIR)


def _load_bin_cache(path: Path) -> Optional[Dict]:
    """Загружает бинарный кэш (pickle). Возвращает None при ошибке."""
    if not path.exists() or path.stat().st_size == 0:
        return None
    try:
        with open(path, 'rb') as f:
            return pickle.load(f)
    except (pickle.PickleError, OSError, EOFError):
        return None


def read_queues_cache() -> List[str]:
    """Читает список очередей из celery_queues.bin или celery_routes_queues.bin."""
    from src.core.utils.cache_fingerprint import mtime_valid, fingerprint_equal

    data = _load_bin_cache(CACHE_FILE)
    if data is not None:
        stored_mtime = data.get('modules_mtime', 0)
        current_mtime = get_modules_config_mtime()
        if mtime_valid(stored_mtime, current_mtime):
            queues = data.get('queues', [])
            if queues:
                return queues
    data = _load_bin_cache(ROUTES_QUEUES_CACHE_FILE)
    if data is not None:
        if fingerprint_equal(data.get('fingerprint', {}), get_fingerprint()):
            queues = data.get('queues', {})
            if queues:
                return sorted(queues.keys())
    return []


def cache_valid() -> bool:
    """Проверяет валидность кэша без загрузки Django."""
    from src.core.utils.cache_fingerprint import mtime_valid, fingerprint_equal

    data = _load_bin_cache(CACHE_FILE)
    if data is not None:
        stored_mtime = data.get('modules_mtime', 0)
        current_mtime = get_modules_config_mtime()
        if mtime_valid(stored_mtime, current_mtime):
            return True
    data = _load_bin_cache(ROUTES_QUEUES_CACHE_FILE)
    if data is not None:
        if fingerprint_equal(data.get('fingerprint', {}), get_fingerprint()):
            return True
    return False


def _acquire_warmup_lock() -> bool:
    """Атомарно создаёт lock-файл. Возвращает True если удалось захватить."""
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    try:
        fd = os.open(str(WARMUP_LOCK), os.O_CREAT | os.O_EXCL | os.O_WRONLY)
        os.write(fd, str(os.getpid()).encode())
        os.close(fd)
        return True
    except FileExistsError:
        return False


def _release_warmup_lock():
    try:
        WARMUP_LOCK.unlink(missing_ok=True)
    except OSError:
        pass


def _is_lock_stale() -> bool:
    """Lock устаревший, если процесс-владелец завершился или файлу больше LOCK_MAX_AGE."""
    try:
        with open(str(WARMUP_LOCK), 'r') as f:
            pid_str = f.read().strip()
        if pid_str.isdigit() and not _pid_exists(int(pid_str)):
            return True
    except OSError:
        pass
    try:
        age = time.time() - WARMUP_LOCK.stat().st_mtime
        return age > LOCK_MAX_AGE
    except OSError:
        return True


def _wait_for_warmup() -> bool:
    """Ждёт завершения warmup другим процессом. Возвращает True если кэш стал валидным (даже при 0 очередях)."""
    while True:
        if not WARMUP_LOCK.exists():
            return cache_valid()
        if _is_lock_stale():
            _release_warmup_lock()
            return False
        time.sleep(0.5)


def ensure_caches() -> List[str]:
    """
    Если кэш пуст — вызывает warmup_caches через Django, затем перечитывает.
    Использует file lock чтобы при параллельном старте N воркеров только один
    процесс загружал Django, остальные ждали результата.
    """
    queues = read_queues_cache()
    # Если кэш уже валиден (даже с 0 очередями) — не пытаемся заново греть Celery.
    if queues or cache_valid():
        return queues

    if _acquire_warmup_lock():
        try:
            print('Celery queues cache is empty. Populating via warmup_celery...')
            result = subprocess.run(
                [sys.executable, '-m', 'commands', 'warmup_celery'],
                cwd=str(API_DIR.parent),
                env={**os.environ, 'PYTHONIOENCODING': 'utf-8', 'PYTHONUTF8': '1'},
            )
            if result.returncode == 0:
                queues = read_queues_cache()
                if cache_valid():
                    print(f'Cache populated: {len(queues)} queues')
                    return queues
            print('[WARNING] Could not populate cache, starting without -Q (all queues)')
        except Exception as e:
            print(f'[WARNING] Could not populate cache ({e}), starting without -Q (all queues)')
        finally:
            _release_warmup_lock()
        return []

    print('Another process is populating cache, waiting...')
    if _wait_for_warmup():
        queues = read_queues_cache()
        print(f'Cache ready: {len(queues)} queues')
        return queues
    print('[WARNING] Cache wait timed out, starting without -Q (all queues)')
    return []


def run_celery_with_timing(
    cmd: List[str],
    cwd: str,
    ready_pattern: str,
    service_name: str,
    start: Optional[float] = None,
) -> int:
    """Запускает celery, выводит лог и печатает время до готовности."""
    if start is None:
        start = time.perf_counter()
    env = os.environ.copy()
    env['PYTHONIOENCODING'] = 'utf-8'
    env['PYTHONUTF8'] = '1'
    proc = subprocess.Popen(
        cmd,
        cwd=cwd,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        encoding='utf-8',
        errors='replace',
        env=env,
    )
    ready_printed = False
    try:
        if proc.stdout:
            for line in proc.stdout:
                print(line, end='')
                if not ready_printed and ready_pattern in line:
                    elapsed = time.perf_counter() - start
                    suffix = 'ms' if elapsed < 1 else 's'
                    val = elapsed * 1000 if elapsed < 1 else elapsed
                    fmt = f'{val:.0f}{suffix}' if elapsed < 1 else f'{val:.2f}{suffix}'
                    print(f'\n>>> {service_name} ready in {fmt}\n')
                    ready_printed = True
        proc.wait()
    except KeyboardInterrupt:
        proc.terminate()
        proc.wait()
    return proc.returncode or 0
