"""Обход процессов без обрыва на недоступной командной строке."""

from __future__ import annotations

from typing import Iterator

import psutil

# WinError 87 (ReadProcessMemory) psutil не переводит в AccessDenied.
_CMDLINE_ERRORS = (
    psutil.NoSuchProcess,
    psutil.AccessDenied,
    psutil.ZombieProcess,
    OSError,
)


def iter_process_cmdlines() -> Iterator[tuple[psutil.Process, list]]:
    """Пары (процесс, argv). Процесс с недоступной командной строкой пропускается.

    process_iter(attrs=['cmdline']) читает argv внутри итератора, до тела цикла.
    На Windows ReadProcessMemory для части процессов даёт WinError 87, и обход
    обрывается целиком. cmdline() вызываем сами и пропускаем такой процесс.
    """
    for proc in psutil.process_iter():
        try:
            cmdline = proc.cmdline() or []
        except _CMDLINE_ERRORS:
            continue
        yield proc, cmdline
