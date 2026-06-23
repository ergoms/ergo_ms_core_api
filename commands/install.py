"""
Команда установки всех зависимостей: ядра и всех модулей.

Использование:
    api install            — установить ядро + все модули
    api install --force    — принудительно переустановить зависимости модулей
"""

import ast
import os
import re
import shutil
import subprocess
import sys
import tempfile
import tomllib
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple

from commands.base import PoetryCommand

_CORE_LOCK_GROUPS = frozenset({"main"})
_PIP_BATCH_SIZE = 40


class InstallCommand(PoetryCommand):
    """
    Устанавливает зависимости ядра через poetry install, затем сканирует
    pyproject.toml всех модулей и доустанавливает недостающие пакеты через pip
    с constraints из poetry.lock ядра (main), чтобы не «перебивать» версии ядра.
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

        print("─── Установка зависимостей ядра (main)...")
        rc = self._install_core(project_root)
        if rc != 0:
            return rc

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

        print(f"\n─── Установка {len(missing)} пакетов из модулей: {', '.join(sorted(missing))}")

        if force:
            self._uninstall_packages(list(missing.keys()))

        rc = self._install_module_packages(project_root, root_data, missing)
        if rc != 0:
            return rc

        print("─── Синхронизация версий пакетов ядра (main)...")
        return self._sync_main_lock_versions(project_root)

    def _install_core(self, project_root: Path) -> int:
        env = os.environ.copy()
        env["POETRY_VIRTUALENVS_CREATE"] = "false"
        result = subprocess.run(
            [
                "poetry",
                "install",
                "--no-root",
                "--only",
                "main",
                "--directory",
                str(project_root),
            ],
            cwd=str(project_root),
            env=env,
        )
        return result.returncode

    def _install_module_packages(
        self, project_root: Path, root_data: dict, module_deps: dict
    ) -> int:
        lock_path = project_root / "poetry.lock"
        main_versions = self._parse_poetry_lock(lock_path, groups=_CORE_LOCK_GROUPS)
        if not main_versions:
            print("Предупреждение: poetry.lock ядра не найден или пуст — constraints не применены.")

        all_sources = self._collect_all_sources(project_root, root_data)
        requirements = [
            self._to_pip_requirement(pkg, constraint, project_root)
            for pkg, constraint in sorted(module_deps.items())
        ]
        extra_index_urls = self._collect_extra_index_urls(module_deps, all_sources)

        tmp_dir = Path(tempfile.mkdtemp(prefix="ergo_install_"))
        try:
            constraints_path = tmp_dir / "core_constraints.txt"
            if main_versions:
                constraints_path.write_text(
                    "\n".join(f"{name}=={version}" for name, version in sorted(main_versions.items()))
                    + "\n",
                    encoding="utf-8",
                )

            cmd: List[str] = [sys.executable, "-m", "pip", "install"]
            for url in extra_index_urls:
                cmd.extend(["--extra-index-url", url])
            if main_versions:
                cmd.extend(["-c", str(constraints_path)])
            cmd.extend(requirements)

            print("Установка модульных пакетов через pip (с constraints poetry.lock ядра)...")
            result = subprocess.run(cmd, cwd=str(project_root))
            return result.returncode
        finally:
            shutil.rmtree(tmp_dir, ignore_errors=True)

    def _sync_main_lock_versions(self, project_root: Path) -> int:
        main_versions = self._parse_poetry_lock(
            project_root / "poetry.lock",
            groups=_CORE_LOCK_GROUPS,
        )
        if not main_versions:
            return 0

        specs = [f"{name}=={version}" for name, version in sorted(main_versions.items())]
        for i in range(0, len(specs), _PIP_BATCH_SIZE):
            batch = specs[i : i + _PIP_BATCH_SIZE]
            result = subprocess.run(
                [sys.executable, "-m", "pip", "install", *batch],
                cwd=str(project_root),
            )
            if result.returncode != 0:
                return result.returncode
        return 0

    def _parse_poetry_lock(
        self, lock_path: Path, groups: Optional[frozenset] = None
    ) -> Dict[str, str]:
        if not lock_path.exists():
            return {}

        versions: Dict[str, str] = {}
        current_name: Optional[str] = None
        current_version: Optional[str] = None
        current_groups: List[str] = []

        def _flush() -> None:
            nonlocal current_name, current_version, current_groups
            if not current_name or not current_version:
                return
            if groups is None or any(group in groups for group in current_groups):
                versions[current_name] = current_version
            current_name = None
            current_version = None
            current_groups = []

        for line in lock_path.read_text(encoding="utf-8").splitlines():
            stripped = line.strip()
            if stripped == "[[package]]":
                _flush()
                continue
            if stripped.startswith("name = "):
                current_name = stripped.split("=", 1)[1].strip().strip('"')
            elif stripped.startswith("version = "):
                current_version = stripped.split("=", 1)[1].strip().strip('"')
            elif stripped.startswith("groups = "):
                try:
                    current_groups = ast.literal_eval(stripped.split("=", 1)[1].strip())
                except (SyntaxError, ValueError):
                    current_groups = []

        _flush()
        return versions

    def _to_pip_requirement(self, pkg: str, constraint: Any, project_root: Path) -> str:
        del project_root
        if isinstance(constraint, str):
            return f"{pkg}{self._pep508_version(constraint)}"
        if isinstance(constraint, dict):
            version = constraint.get("version", "")
            if version:
                return f"{pkg}{self._pep508_version(version)}"
        return pkg

    def _pep508_version(self, constraint: str) -> str:
        value = constraint.strip()
        if not value:
            return ""

        if value.startswith("^"):
            base = value[1:]
            major = int(base.split(".", 1)[0])
            if major == 0:
                parts = base.split(".")
                minor = int(parts[1]) if len(parts) > 1 else 0
                return f">={base},<0.{minor + 1}.0"
            return f">={base},<{major + 1}.0.0"

        if value.startswith("~"):
            base = value[1:]
            parts = base.split(".")
            if len(parts) >= 2:
                return f">={base},<{parts[0]}.{int(parts[1]) + 1}.0"
            return f">={base}"

        if re.match(r"^[<>=!~]", value):
            return value

        return f"=={value}"

    def _collect_extra_index_urls(
        self, module_deps: dict, all_sources: List[dict]
    ) -> List[str]:
        source_urls = {source["name"]: source["url"] for source in all_sources}
        urls: List[str] = []
        seen: Set[str] = set()
        for constraint in module_deps.values():
            if not isinstance(constraint, dict):
                continue
            source_name = constraint.get("source")
            if not source_name:
                continue
            url = source_urls.get(source_name)
            if url and url not in seen:
                seen.add(url)
                urls.append(url)
        return urls

    def _uninstall_packages(self, packages: List[str]) -> None:
        print(f"Удаление {len(packages)} пакетов перед переустановкой...")
        subprocess.run(
            [sys.executable, "-m", "pip", "uninstall", "-y", *packages],
        )

    def _find_project_root(self) -> Optional[Path]:
        candidates = [
            Path(os.getcwd()),
            Path(__file__).resolve().parent.parent.parent.parent,
        ]
        for candidate in candidates:
            if (candidate / "pyproject.toml").exists():
                return candidate
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
        match = re.search(r"(\d+)(?:\.(\d+))?(?:\.(\d+))?", constraint)
        if match:
            return tuple(int(part or 0) for part in match.groups())
        return (0, 0, 0)
