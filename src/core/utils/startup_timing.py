"""
Учёт времени запуска API, Celery worker и Beat.
"""

import time

_start_time: float | None = None


def mark_start() -> None:
    """Отмечает начало запуска (вызывается из manage.py)."""
    global _start_time
    _start_time = time.perf_counter()


def set_start_time_if_earlier(t: float) -> None:
    """Устанавливает время старта, если ещё не установлено или t раньше."""
    global _start_time
    if _start_time is None or t < _start_time:
        _start_time = t


def get_elapsed() -> float:
    """Возвращает время в секундах с момента mark_start()."""
    if _start_time is None:
        return 0.0
    return time.perf_counter() - _start_time


def get_elapsed_str() -> str:
    """Возвращает строку вида 'in 12.34s' (ASCII для совместимости с консолью)."""
    elapsed = get_elapsed()
    if elapsed < 1:
        return f"in {elapsed * 1000:.0f}ms"
    return f"in {elapsed:.2f}s"
