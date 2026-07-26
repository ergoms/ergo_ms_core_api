"""
Команда обновления зависимостей: ядро (poetry update) и модули (pip upgrade).

Использование:
    api update                 — обновить ядро и все модульные пакеты
    api update <пакет> ...     — обновить указанные пакеты (ядро и/или модули)
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any, Dict, List

from packaging.utils import canonicalize_name

from commands.base import PoetryCommand
from commands.install import (
    InstallCommand,
    _CORE_LOCK_GROUPS,
    _NO_DEPS_PACKAGES,
    _NO_DEPS_RUNTIME_DEPS,
)


class UpdateCommand(PoetryCommand):
    """Обновляет poetry.lock/ядро и пакеты из pyproject.toml модулей."""

    poetry_command_name = "update"
    script_command = "update"

    def run(self, *args) -> int:
        flags = [a for a in args if a.startswith("-")]
        packages = [a for a in args if a and not a.startswith("-")]

        installer = InstallCommand()
        project_root = installer._find_project_root()
        if project_root is None:
            print("Ошибка: не удалось найти корневой pyproject.toml.")
            return 1

        root_data = installer._read_toml(project_root / "pyproject.toml")
        if root_data is None:
            return 1

        root_deps = installer._get_poetry_deps(root_data)
        root_canon = {
            canonicalize_name(name)
            for name in root_deps
            if name != "python"
        }

        module_configs = installer._scan_module_configs(project_root)
        module_only: Dict[str, Any] = {}
        if module_configs:
            merged_deps, conflicts = installer._merge_dependencies(
                root_data, module_configs
            )
            if conflicts:
                print("\nКонфликты версий (применена более строгая):")
                for pkg, sources in conflicts.items():
                    for src, ver in sources.items():
                        print(f"  {pkg} [{src}]: {ver}")
            module_only = {
                pkg: constraint
                for pkg, constraint in merged_deps.items()
                if pkg != "python" and pkg not in root_deps
            }

        module_canon = {
            canonicalize_name(name): name for name in module_only
        }

        core_packages: List[str] = []
        module_packages: Dict[str, Any] = {}

        if not packages:
            module_packages = dict(module_only)
            update_core = True
        else:
            update_core = False
            for pkg in packages:
                key = canonicalize_name(pkg)
                if key in module_canon:
                    original = module_canon[key]
                    module_packages[original] = module_only[original]
                if key in root_canon or key not in module_canon:
                    core_packages.append(pkg)
                    update_core = True

        if update_core:
            print("─── Обновление зависимостей ядра (poetry update)...")
            rc = self._poetry_update(project_root, core_packages, flags)
            if rc != 0:
                return rc
        else:
            print("─── В ядре указанных пакетов нет — poetry update пропущен.")

        if module_packages:
            print(
                f"─── Обновление {len(module_packages)} пакетов модулей: "
                f"{', '.join(sorted(module_packages))}"
            )
            rc = self._upgrade_module_packages(
                installer, project_root, root_data, module_packages
            )
            if rc != 0:
                return rc
        else:
            print("─── Дополнительных зависимостей модулей для обновления нет.")

        rc = installer._sync_main_lock_versions(project_root)
        if rc != 0:
            return rc

        rc = installer._remove_orphaned_packages(project_root, module_only)
        if rc != 0:
            return rc

        return installer._prune_unused_dep_caches(project_root, module_only)

    def _poetry_update(
        self,
        project_root: Path,
        packages: List[str],
        flags: List[str],
    ) -> int:
        env = os.environ.copy()
        env["POETRY_VIRTUALENVS_CREATE"] = "false"
        cmd = [
            "poetry",
            "update",
            "--only",
            "main",
            "--no-interaction",
            "--directory",
            str(project_root),
            *flags,
            *packages,
        ]
        result = subprocess.run(cmd, cwd=str(project_root), env=env)
        return result.returncode

    def _upgrade_module_packages(
        self,
        installer: InstallCommand,
        project_root: Path,
        root_data: dict,
        module_deps: Dict[str, Any],
    ) -> int:
        main_versions = installer._parse_poetry_lock(
            project_root / "poetry.lock",
            groups=_CORE_LOCK_GROUPS,
        )

        regular_deps = {
            pkg: constraint
            for pkg, constraint in module_deps.items()
            if pkg not in _NO_DEPS_PACKAGES
        }
        no_deps_packages = {
            pkg: constraint
            for pkg, constraint in module_deps.items()
            if pkg in _NO_DEPS_PACKAGES
        }

        all_sources = installer._collect_all_sources(project_root, root_data)
        extra_index_urls = installer._collect_extra_index_urls(
            module_deps, all_sources
        )

        if regular_deps:
            specs = [
                installer._to_pip_requirement(pkg, constraint, project_root)
                for pkg, constraint in sorted(regular_deps.items())
            ]
            cmd: List[str] = [
                sys.executable,
                "-m",
                "pip",
                "install",
                "--upgrade",
                *specs,
            ]
            for url in extra_index_urls:
                cmd.extend(["--extra-index-url", url])

            pip_env = os.environ.copy()
            pip_cache = project_root / "virtual_env" / "cache" / "pip"
            poetry_cache = project_root / "virtual_env" / "cache" / "poetry"
            pip_cache.mkdir(parents=True, exist_ok=True)
            poetry_cache.mkdir(parents=True, exist_ok=True)
            pip_env["PIP_CACHE_DIR"] = str(pip_cache)
            pip_env["POETRY_CACHE_DIR"] = str(poetry_cache)

            cache_tmp = project_root / "virtual_env" / "cache" / "tmp"
            cache_tmp.mkdir(parents=True, exist_ok=True)
            tmp_dir = Path(
                tempfile.mkdtemp(prefix="ergo_update_", dir=str(cache_tmp))
            )
            try:
                if main_versions:
                    constraints_path = tmp_dir / "core_constraints.txt"
                    installer._write_core_constraints(
                        constraints_path, main_versions
                    )
                    cmd.extend(["-c", str(constraints_path)])
                print(
                    "pip install --upgrade модульных пакетов "
                    "(constraints: poetry.lock ядра)..."
                )
                result = subprocess.run(
                    cmd, cwd=str(project_root), env=pip_env
                )
                if result.returncode != 0:
                    return result.returncode
            finally:
                shutil.rmtree(tmp_dir, ignore_errors=True)

        for pkg, constraint in sorted(no_deps_packages.items()):
            req_line = installer._to_pip_requirement(
                pkg, constraint, project_root
            )
            runtime_deps = _NO_DEPS_RUNTIME_DEPS.get(pkg, [])
            if runtime_deps:
                result = subprocess.run(
                    [
                        sys.executable,
                        "-m",
                        "pip",
                        "install",
                        "--upgrade",
                        *runtime_deps,
                    ],
                    cwd=str(project_root),
                )
                if result.returncode != 0:
                    return result.returncode
            cmd = [
                sys.executable,
                "-m",
                "pip",
                "install",
                "--upgrade",
                "--no-deps",
                req_line,
            ]
            for url in extra_index_urls:
                cmd.extend(["--extra-index-url", url])
            result = subprocess.run(cmd, cwd=str(project_root))
            if result.returncode != 0:
                return result.returncode

        return 0
