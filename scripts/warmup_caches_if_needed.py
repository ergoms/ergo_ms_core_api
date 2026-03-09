"""
Прогрев кэшей только при необходимости.

Проверяет celery_queues.json / celery_routes_queues.json без Django.
Если кэш валиден — выход за миллисекунды. Иначе — вызывает warmup_caches (Django).
"""

import os
import subprocess
import sys

from _common import API_DIR, cache_valid


def main() -> int:
    if cache_valid():
        return 0
    result = subprocess.run(
        [sys.executable, '-m', 'commands', 'warmup_caches'],
        cwd=str(API_DIR.parent),
        timeout=60,
        env={**os.environ, 'PYTHONIOENCODING': 'utf-8', 'PYTHONUTF8': '1'},
    )
    return result.returncode


if __name__ == '__main__':
    sys.exit(main())
