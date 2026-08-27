"""Замена текущего процесса на команду сервера (без висящего родителя)."""

from __future__ import annotations

import os
import subprocess
from collections.abc import Mapping, Sequence


def replace_current_process(
    cmd: Sequence[str],
    *,
    cwd: str | os.PathLike[str] | None = None,
    env: Mapping[str, str] | None = None,
) -> int:
    """execvpe; если замена не удалась — subprocess.call."""
    argv = [str(part) for part in cmd]
    if not argv:
        return 2
    run_env = dict(env) if env is not None else os.environ.copy()
    if cwd:
        os.chdir(str(cwd))
    try:
        os.execvpe(argv[0], argv, run_env)
    except OSError:
        return subprocess.call(argv, env=run_env)
    return 1
