"""
Команды прогрева файловых кэшей без django.setup().
"""

from __future__ import annotations

from commands.base import PoetryCommand
from src.core.utils.warmup_file_caches import run_file_cache_warmup


def _print_warmup_result(result: dict, *, celery_only: bool) -> None:
    print(f"Обнаружено приложений: {result['apps']}")
    print(f"Celery: {result['routes']} маршрутов, {result['queues']} очередей")
    print(f"Расписание Beat: {result['beat_tasks']} задач")
    if not celery_only and result.get('modules_env'):
        print(f"Переменные модулей: {result['modules_env']}")
    label = 'Celery кэши прогреты' if celery_only else 'Все кэши прогреты'
    print(f"{label} ({result['elapsed_sec']:.2f}s)")


class WarmupCachesCommand(PoetryCommand):
    """Прогрев всех файловых кэшей (в т.ч. modules_env)."""

    poetry_command_name = 'warmup_caches'
    script_command = 'warmup_caches'

    def run(self, *args) -> int:
        result = run_file_cache_warmup(include_modules_env=True)
        _print_warmup_result(result, celery_only=False)
        return 0


class WarmupCeleryCommand(PoetryCommand):
    """Прогрев celery-кэшей без modules_env."""

    poetry_command_name = 'warmup_celery'
    script_command = 'warmup_celery'

    def run(self, *args) -> int:
        result = run_file_cache_warmup(include_modules_env=False)
        _print_warmup_result(result, celery_only=True)
        return 0
