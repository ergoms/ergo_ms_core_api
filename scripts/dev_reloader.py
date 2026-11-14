"""
Горячая перезагрузка API в development без второй загрузки Django.

Встроенный autoreload runserver грузит весь проект дважды: в процессе-наблюдателе
и в рабочем процессе. Здесь наблюдатель не импортирует Django: он опрашивает
mtime файлов .py ядра и modules/<name>/api и перезапускает `commands dev --noreload`.
"""

from __future__ import annotations

import subprocess
import time
from collections.abc import Mapping, Sequence
from pathlib import Path

from _common import format_console

from src.core.utils.autoreload_paths import dev_watch_roots, snapshot_dev_watch_files

_POLL_SEC = 1.0
# Редактор сохраняет несколько файлов подряд: ждём, пока запись закончится.
_SETTLE_SEC = 0.3
_STOP_TIMEOUT_SEC = 10


def _log(level: str, message: str) -> None:
    print(format_console(level, message), flush=True)


def _changed_paths(before: dict[str, int], after: dict[str, int]) -> list[str]:
    changed = [path for path, mtime in after.items() if before.get(path) != mtime]
    changed.extend(path for path in before if path not in after)
    return changed


def _stop(proc: subprocess.Popen | None) -> None:
    if proc is None or proc.poll() is not None:
        return
    proc.terminate()
    try:
        proc.wait(timeout=_STOP_TIMEOUT_SEC)
    except subprocess.TimeoutExpired:
        proc.kill()
        proc.wait()


def _relative(path: str, project_root: Path) -> str:
    try:
        return Path(path).relative_to(project_root).as_posix()
    except ValueError:
        return path


def run_dev_with_reloader(
    cmd: Sequence[str],
    *,
    cwd: str,
    env: Mapping[str, str],
    project_root: Path,
    start_env_key: str,
) -> int:
    """Держит рабочий процесс API и перезапускает его при правке серверного кода."""
    roots = dev_watch_roots(project_root)
    snapshot = snapshot_dev_watch_files(roots)
    _log('info', f'Горячая перезагрузка API: {len(snapshot)} файлов .py в {len(roots)} каталогах')

    def _spawn(first: bool) -> subprocess.Popen:
        run_env = dict(env)
        if not first:
            # Время готовности после перезапуска считается заново.
            run_env[start_env_key] = str(time.time())
        return subprocess.Popen([str(part) for part in cmd], cwd=cwd, env=run_env)

    proc: subprocess.Popen | None = _spawn(first=True)
    try:
        while True:
            time.sleep(_POLL_SEC)
            if proc is not None:
                code = proc.poll()
                if code == 0:
                    return 0
                if code is not None:
                    _log('error', f'API завершился с кодом {code}. Перезапуск после правки файла.')
                    proc = None

            current = snapshot_dev_watch_files(roots)
            changed = _changed_paths(snapshot, current)
            if not changed:
                continue
            time.sleep(_SETTLE_SEC)
            snapshot = snapshot_dev_watch_files(roots)
            shown = _relative(changed[0], project_root)
            more = f' и ещё {len(changed) - 1}' if len(changed) > 1 else ''
            _log('info', f'Изменён {shown}{more}, перезапуск API')
            _stop(proc)
            proc = _spawn(first=False)
    except KeyboardInterrupt:
        return 0
    finally:
        _stop(proc)
