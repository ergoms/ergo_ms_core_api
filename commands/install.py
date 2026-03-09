"""
Команда установки всех зависимостей: ядра и всех модулей.

Использование:
    api install            — установить ядро + все модули
    api install --force    — принудительно переустановить зависимости модулей
"""

import os
import re
import shutil
import subprocess
import sys
import tempfile
import tomllib
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from commands.base import PoetryCommand


class InstallCommand(PoetryCommand):
    """
    Устанавливает зависимости ядра через poetry install, затем сканирует
    pyproject.toml всех модулей и доустанавливает недостающие пакеты.
    Корневой pyproject.toml при этом не изменяется.
    """

    poetry_command_name = "install"
    script_command = "install"

    def run(self, *args) -> int:
        force = "--force" in args

        project_root = self._find_project_root()
        if project_root is None:
            print("Ошибка: не удалось найти корневой pyproject.toml.")
            return 1

        # ── 1. Устанавливаем ядро ────────────────────────────────────────
        print("─── Установка зависимостей ядра...")
        rc = self._install_core(project_root)
        if rc != 0:
            return rc

        # ── 2. Собираем зависимости модулей ──────────────────────────────
        root_data = self._read_toml(project_root / "pyproject.toml")
        if root_data is None:
            return 1

        module_configs = self._scan_module_configs(project_root)
        if not module_configs:
            print("Модульных pyproject.toml не найдено — установка завершена.")
            return 0

        merged_deps, conflicts = self._merge_dependencies(root_data, module_configs)

        if conflicts:
            print("\nКонфликты версий (применена более строгая):")
            for pkg, sources in conflicts.items():
                for src, ver in sources.items():
                    print(f"  {pkg} [{src}]: {ver}")

        root_deps = self._get_poetry_deps(root_data)
        missing = {
            pkg: constraint
            for pkg, constraint in merged_deps.items()
            if pkg != "python" and pkg not in root_deps
        }

        if not missing:
            print("─── Все зависимости модулей уже установлены.")
            return 0

        # ── 3. Устанавливаем зависимости модулей ─────────────────────────
        print(f"\n─── Установка {len(missing)} пакетов из модулей: {', '.join(sorted(missing))}")

        if force:
            self._uninstall_packages(list(missing.keys()))

        return self._install_via_poetry(project_root, root_data, missing)

    # ------------------------------------------------------------------ #
    # Шаг 1: установка ядра                                               #
    # ------------------------------------------------------------------ #

    def _install_core(self, project_root: Path) -> int:
        env = os.environ.copy()
        env["POETRY_VIRTUALENVS_CREATE"] = "false"
        result = subprocess.run(
            ["poetry", "install", "--no-root", "--directory", str(project_root)],
            cwd=str(project_root),
            env=env,
        )
        return result.returncode

    # ------------------------------------------------------------------ #
    # Шаг 3: установка через временный pyproject.toml                     #
    # ------------------------------------------------------------------ #

    def _install_via_poetry(
        self, project_root: Path, root_data: dict, merged_deps: dict
    ) -> int:
        all_sources = self._collect_all_sources(project_root, root_data)
        tmp_dir = Path(tempfile.mkdtemp(prefix="ergo_install_"))
        try:
            toml_content = self._build_merged_toml(root_data, merged_deps, project_root, all_sources)
            (tmp_dir / "pyproject.toml").write_text(toml_content, encoding="utf-8")

            lock_src = project_root / "poetry.lock"
            if lock_src.exists():
                shutil.copy2(lock_src, tmp_dir / "poetry.lock")

            env = os.environ.copy()
            env["POETRY_VIRTUALENVS_CREATE"] = "false"

            print("Обновление poetry.lock для новых пакетов...")
            lock_result = subprocess.run(
                ["poetry", "lock", "--directory", str(tmp_dir)],
                cwd=str(project_root),
                env=env,
            )
            if lock_result.returncode != 0:
                return lock_result.returncode

            result = subprocess.run(
                ["poetry", "install", "--no-root", "--directory", str(tmp_dir)],
                cwd=str(project_root),
                env=env,
            )
            return result.returncode
        finally:
            shutil.rmtree(tmp_dir, ignore_errors=True)

    def _uninstall_packages(self, packages: List[str]) -> None:
        print(f"Удаление {len(packages)} пакетов перед переустановкой...")
        subprocess.run(
            [sys.executable, "-m", "pip", "uninstall", "-y", *packages],
        )

    # ------------------------------------------------------------------ #
    # Чтение / сканирование                                               #
    # ------------------------------------------------------------------ #

    def _find_project_root(self) -> Optional[Path]:
        candidates = [
            Path(os.getcwd()),
            Path(__file__).resolve().parent.parent.parent.parent,
        ]
        for c in candidates:
            if (c / "pyproject.toml").exists():
                return c
        return None

    def _read_toml(self, path: Path) -> Optional[dict]:
        try:
            with open(path, "rb") as f:
                return tomllib.load(f)
        except Exception as e:
            print(f"Ошибка чтения {path}: {e}")
            return None

    def _get_poetry_deps(self, data: dict) -> dict:
        return data.get("tool", {}).get("poetry", {}).get("dependencies", {})

    def _scan_module_configs(self, project_root: Path) -> List[Tuple[str, dict]]:
        modules_dir = project_root / "modules"
        results: List[Tuple[str, dict]] = []
        if not modules_dir.exists():
            return results
        for module_dir in sorted(modules_dir.iterdir()):
            if not module_dir.is_dir():
                continue
            config_path = module_dir / "pyproject.toml"
            if not config_path.exists():
                continue
            data = self._read_toml(config_path)
            if data:
                deps = self._get_poetry_deps(data)
                if deps:
                    results.append((module_dir.name, deps))
        return results

    def _collect_all_sources(self, project_root: Path, root_data: dict) -> List[dict]:
        seen: Dict[str, dict] = {}
        for source in root_data.get("tool", {}).get("poetry", {}).get("source", []):
            seen[source["name"]] = source
        modules_dir = project_root / "modules"
        if modules_dir.exists():
            for module_dir in sorted(modules_dir.iterdir()):
                config_path = module_dir / "pyproject.toml"
                if not config_path.exists():
                    continue
                data = self._read_toml(config_path)
                if not data:
                    continue
                for source in data.get("tool", {}).get("poetry", {}).get("source", []):
                    seen.setdefault(source["name"], source)
        return list(seen.values())

    # ------------------------------------------------------------------ #
    # Слияние зависимостей                                                #
    # ------------------------------------------------------------------ #

    def _merge_dependencies(
        self,
        root_data: dict,
        module_configs: List[Tuple[str, dict]],
    ) -> Tuple[dict, dict]:
        root_deps = self._get_poetry_deps(root_data)
        merged: Dict[str, Any] = dict(root_deps)
        conflicts: Dict[str, Dict[str, Any]] = {}

        for module_name, module_deps in module_configs:
            for pkg, constraint in module_deps.items():
                if pkg == "python":
                    continue
                if pkg not in merged:
                    merged[pkg] = constraint
                elif merged[pkg] != constraint:
                    if pkg not in conflicts:
                        conflicts[pkg] = {"(текущее)": merged[pkg]}
                    conflicts[pkg][module_name] = constraint
                    merged[pkg] = self._resolve_conflict(merged[pkg], constraint)

        return merged, conflicts

    def _resolve_conflict(self, a: Any, b: Any) -> Any:
        if isinstance(a, dict) and not isinstance(b, dict):
            return a
        if isinstance(b, dict) and not isinstance(a, dict):
            return b
        try:
            return a if self._lower_ver(str(a)) >= self._lower_ver(str(b)) else b
        except Exception:
            return a

    def _lower_ver(self, constraint: str) -> tuple:
        m = re.search(r"(\d+)(?:\.(\d+))?(?:\.(\d+))?", constraint)
        if m:
            return tuple(int(x or 0) for x in m.groups())
        return (0, 0, 0)

    # ------------------------------------------------------------------ #
    # Построение временного pyproject.toml                                #
    # ------------------------------------------------------------------ #

    def _build_merged_toml(
        self,
        root_data: dict,
        module_only_deps: dict,
        project_root: Path,
        extra_sources: Optional[List[dict]] = None,
    ) -> str:
        """
        Строит минимальный временный pyproject.toml только с зависимостями модулей.
        Корневые зависимости (включая path-пакеты django/drf) сюда не включаются —
        они уже установлены шагом poetry install для ядра.
        """
        poetry_section = root_data.get("tool", {}).get("poetry", {})
        sources: list = extra_sources if extra_sources is not None else []
        build_system: dict = root_data.get("build-system", {})

        lines: List[str] = []
        lines.append("[tool.poetry]")
        lines.append('name = "ergo_ms_modules"')
        lines.append('version = "0.1.0"')
        lines.append("")

        for source in sources:
            lines.append("[[tool.poetry.source]]")
            for k, v in source.items():
                lines.append(f'{k} = "{v}"')
            lines.append("")

        python_constraint = (
            root_data.get("tool", {})
            .get("poetry", {})
            .get("dependencies", {})
            .get("python", ">=3.12,<3.13")
        )
        lines.append("[tool.poetry.dependencies]")
        lines.append(f'python = "{python_constraint}"')
        for pkg, constraint in sorted(module_only_deps.items()):
            if pkg == "python":
                continue
            lines.append(f"{pkg} = {self._format_constraint(constraint, project_root)}")
        lines.append("")

        if build_system:
            lines.append("[build-system]")
            requires = build_system.get("requires", [])
            if requires:
                req_str = ", ".join(f'"{r}"' for r in requires)
                lines.append(f"requires = [{req_str}]")
            if "build-backend" in build_system:
                lines.append(f'build-backend = "{build_system["build-backend"]}"')

        return "\n".join(lines) + "\n"

    def _format_constraint(self, constraint: Any, project_root: Path) -> str:
        if isinstance(constraint, str):
            return f'"{constraint}"'
        if isinstance(constraint, dict):
            parts: List[str] = []
            for k, v in constraint.items():
                if k == "path":
                    abs_path = (project_root / v).resolve().as_posix()
                    parts.append(f'path = "{abs_path}"')
                elif k == "extras":
                    ext_str = ", ".join(f'"{e}"' for e in v)
                    parts.append(f"extras = [{ext_str}]")
                elif isinstance(v, bool):
                    parts.append(f"{k} = {'true' if v else 'false'}")
                elif isinstance(v, str):
                    parts.append(f'{k} = "{v}"')
                else:
                    parts.append(f"{k} = {v}")
            return "{" + ", ".join(parts) + "}"
        return str(constraint)
