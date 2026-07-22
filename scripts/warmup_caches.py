"""
Прогрев файловых кэшей без django.setup().

Использование:
  python scripts/warmup_caches.py
  python scripts/warmup_caches.py --celery-only
"""

from __future__ import annotations

import sys
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
API_DIR = SCRIPT_DIR.parent
if str(API_DIR) not in sys.path:
    sys.path.insert(0, str(API_DIR))

from src.core.utils.warmup_file_caches import run_file_cache_warmup  # noqa: E402


def main(argv: list[str] | None = None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    celery_only = '--celery-only' in args
    result = run_file_cache_warmup(include_modules_env=not celery_only)
    print(f"Обнаружено приложений: {result['apps']}")
    print(f"Celery: {result['routes']} маршрутов, {result['queues']} очередей")
    print(f"Расписание Beat: {result['beat_tasks']} задач")
    if not celery_only and result.get('modules_env'):
        print(f"Переменные модулей: {result['modules_env']}")
    label = 'Celery кэши прогреты' if celery_only else 'Все кэши прогреты'
    print(f"{label} ({result['elapsed_sec']:.2f}s)")
    return 0


if __name__ == '__main__':
    sys.exit(main())
