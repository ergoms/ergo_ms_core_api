"""Очистка кэшей pip/Poetry/tmp от артефактов пакетов, которых нет в зависимостях."""

from __future__ import annotations

import os
import re
import shutil
import site
import subprocess
import sys
from pathlib import Path
from typing import Iterable, List, Set

from packaging.utils import canonicalize_name

_WHEEL_NAME_RE = re.compile(
    r"^(?P<name>.+?)-(?P<ver>\d[^-]*)(?:-.*)?\.(?:whl|tar\.gz|zip)$",
    re.IGNORECASE,
)
_TMP_PREFIXES = ("ergo_install_", "ergo_update_", "ergo-npm-", "ergo_npm_")


def prune_python_dep_caches(project_root: Path, desired_packages: Iterable[str]) -> None:
    """Удаляет из virtual_env/cache копии пакетов вне desired + HTTP/tmp мусор."""
    desired = {canonicalize_name(name) for name in desired_packages if name}
    _clean_pip_uninstall_leftovers()

    cache_root = project_root / "virtual_env" / "cache"
    if not cache_root.is_dir():
        return

    _clean_cache_tmp(cache_root / "tmp")
    _prune_pip_wheel_cache(project_root, desired)
    _prune_poetry_artifacts(cache_root / "poetry" / "artifacts", desired)
    # HTTP-кэши pip/Poetry — hash-хранилище без привязки к имени пакета;
    # выборочно не почистить, они и дают гигабайты «мёртвого» кэша.
    _clear_opaque_dir(
        cache_root / "pip" / "http-v2",
        label="кэш pip HTTP (http-v2)",
    )
    _clear_opaque_dir(
        cache_root / "pip" / "http",
        label="кэш pip HTTP (http)",
    )
    _clear_poetry_http_caches(cache_root / "poetry" / "cache")


def _site_packages_roots() -> List[Path]:
    roots: List[Path] = []
    try:
        for raw in site.getsitepackages():
            path = Path(raw)
            if path.is_dir():
                roots.append(path)
    except Exception:
        pass
    fallback = Path(sys.prefix) / "Lib" / "site-packages"
    if fallback.is_dir() and fallback not in roots:
        roots.append(fallback)
    return roots


def _clean_pip_uninstall_leftovers() -> None:
    """Удаляет leftover pip на Windows: каталоги/файлы с именем, начинающимся на '~'."""
    leftovers: List[Path] = []
    for root in _site_packages_roots():
        for path in root.rglob("~*"):
            leftovers.append(path)

    if not leftovers:
        return

    leftovers.sort(key=lambda p: len(p.parts), reverse=True)
    removed = 0
    failed = 0
    for path in leftovers:
        if not path.exists():
            continue
        try:
            if path.is_dir():
                shutil.rmtree(path)
            else:
                path.unlink(missing_ok=True)
            removed += 1
        except OSError:
            failed += 1

    if removed:
        print(
            f"─── Очистка site-packages: удалено {removed} "
            "временных путей pip (~*)."
        )
    if failed:
        print(
            f"─── Предупреждение: не удалось удалить {failed} leftover pip "
            "(файлы заняты процессом - остановите API/worker и повторите)."
        )


def _clean_cache_tmp(tmp_dir: Path) -> None:
    if not tmp_dir.is_dir():
        return
    removed = 0
    for entry in tmp_dir.iterdir():
        if not any(entry.name.startswith(prefix) for prefix in _TMP_PREFIXES):
            continue
        try:
            if entry.is_dir():
                shutil.rmtree(entry, ignore_errors=True)
            else:
                entry.unlink(missing_ok=True)
            removed += 1
        except OSError:
            continue
    if removed:
        print(f"─── Очистка virtual_env/cache/tmp: удалено {removed} временных путей.")


def _dir_size_bytes(path: Path) -> int:
    if not path.exists():
        return 0
    total = 0
    if path.is_file():
        try:
            return path.stat().st_size
        except OSError:
            return 0
    for file_path in path.rglob("*"):
        if file_path.is_file():
            try:
                total += file_path.stat().st_size
            except OSError:
                continue
    return total


def _format_mb(num_bytes: int) -> str:
    return f"{num_bytes / (1024 * 1024):.1f} MB"


def _clear_opaque_dir(path: Path, *, label: str) -> None:
    if not path.exists():
        return
    size = _dir_size_bytes(path)
    try:
        if path.is_dir():
            shutil.rmtree(path)
        else:
            path.unlink(missing_ok=True)
    except OSError as exc:
        print(f"─── Предупреждение: не удалось очистить {label}: {exc}")
        return
    if size > 0:
        print(f"─── Очистка {label}: освобождено {_format_mb(size)}.")


def _clear_poetry_http_caches(poetry_cache_dir: Path) -> None:
    if not poetry_cache_dir.is_dir():
        return
    freed = 0
    removed_dirs = 0
    for http_dir in poetry_cache_dir.rglob("_http_"):
        if not http_dir.is_dir():
            continue
        size = _dir_size_bytes(http_dir)
        try:
            shutil.rmtree(http_dir)
            freed += size
            removed_dirs += 1
        except OSError:
            continue
    if removed_dirs:
        print(
            f"─── Очистка кэша Poetry HTTP: удалено каталогов {removed_dirs}, "
            f"освобождено {_format_mb(freed)}."
        )
    else:
        print("─── Кэш Poetry HTTP: очищать нечего.")


def _pip_cache_env(project_root: Path) -> dict:
    env = os.environ.copy()
    pip_cache = project_root / "virtual_env" / "cache" / "pip"
    pip_cache.mkdir(parents=True, exist_ok=True)
    env["PIP_CACHE_DIR"] = str(pip_cache)
    return env


def _prune_pip_wheel_cache(project_root: Path, desired: Set[str]) -> None:
    env = _pip_cache_env(project_root)
    listed = subprocess.run(
        [sys.executable, "-m", "pip", "cache", "list", "--format=abspath"],
        capture_output=True,
        text=True,
        env=env,
    )
    if listed.returncode != 0 or not listed.stdout.strip():
        print("─── Кэш pip (wheels): пуст.")
        return

    # pip cache remove ждёт имя distribution как в wheel (часто с `_`).
    unused_raw: Set[str] = set()
    unused_canon: Set[str] = set()
    for line in listed.stdout.splitlines():
        path_text = line.strip()
        if not path_text:
            continue
        filename = Path(path_text).name
        raw_name, canon_name = _package_names_from_artifact(filename)
        if canon_name and canon_name not in desired and raw_name:
            unused_raw.add(raw_name)
            unused_canon.add(canon_name)

    if not unused_raw:
        print("─── Кэш pip (wheels): лишних пакетов нет.")
        return

    print(
        f"─── Кэш pip (wheels): удаление {len(unused_canon)} неиспользуемых: "
        f"{', '.join(sorted(unused_canon))}"
    )
    for name in sorted(unused_raw):
        subprocess.run(
            [sys.executable, "-m", "pip", "cache", "remove", name],
            capture_output=True,
            text=True,
            env=env,
        )


def _package_names_from_artifact(filename: str) -> tuple[str | None, str | None]:
    """(raw distribution name для pip cache, canonical name)."""
    match = _WHEEL_NAME_RE.match(filename)
    if not match:
        return None, None
    raw_name = match.group("name")
    return raw_name, canonicalize_name(raw_name)


def _prune_poetry_artifacts(artifacts_dir: Path, desired: Set[str]) -> None:
    if not artifacts_dir.is_dir():
        return

    removed = 0
    freed = 0
    for path in artifacts_dir.rglob("*"):
        if not path.is_file():
            continue
        _raw, name = _package_names_from_artifact(path.name)
        if name is None or name in desired:
            continue
        try:
            freed += path.stat().st_size
            path.unlink(missing_ok=True)
            removed += 1
        except OSError:
            continue

    for directory in sorted(
        (p for p in artifacts_dir.rglob("*") if p.is_dir()),
        key=lambda p: len(p.parts),
        reverse=True,
    ):
        try:
            if not any(directory.iterdir()):
                directory.rmdir()
        except OSError:
            continue

    if removed:
        print(
            f"─── Кэш Poetry (artifacts): удалено {removed} файлов "
            f"({_format_mb(freed)}) неиспользуемых пакетов."
        )
    else:
        print("─── Кэш Poetry (artifacts): лишних пакетов нет.")
