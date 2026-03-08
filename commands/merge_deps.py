"""
Команда для слияния зависимостей всех модулей и их установки в общий venv.

Использование:
    api merge-deps               — показать итоговые зависимости (dry-run)
    api merge-deps --install     — установить недостающие зависимости через poetry
    api merge-deps --reinstall   — удалить модульные пакеты и поставить заново через poetry
    api merge-deps --check       — завершиться с ошибкой при наличии конфликтов
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


class MergeDepsCommand(PoetryCommand):
    """
    Сканирует pyproject.toml всех модулей, сливает их зависимости с корневым
    pyproject.toml и при необходимости устанавливает недостающие пакеты.
    """

    poetry_command_name = "merge-deps"
    script_command = "merge-deps"

    # ------------------------------------------------------------------ #
    # Entry point                                                          #
    # ------------------------------------------------------------------ #

    def run(self, *args) -> int:
        install_mode = "--install" in args
        reinstall_mode = "--reinstall" in args
        check_mode = "--check" in args

        project_root = self._find_project_root()
        if project_root is None:
            print("Ошибка: не удалось найти корневой pyproject.toml.")
            return 1

        root_data = self._read_toml(project_root / "pyproject.toml")
        if root_data is None:
            return 1

        module_configs = self._scan_module_configs(project_root)
        if not module_configs:
            print("Модульных pyproject.toml не найдено.")
            return 0

        merged_deps, conflicts = self._merge_dependencies(root_data, module_configs)

        if conflicts:
            print("Конфликты версий:")
            for pkg, sources in conflicts.items():
                print(f"  {pkg}:")
                for src, ver in sources.items():
                    print(f"    {src}: {ver}")
            if check_mode:
                return 1

        if install_mode or reinstall_mode:
            return self._install_missing(
                project_root, root_data, merged_deps, force=reinstall_mode
            )

        self._print_merged_deps(merged_deps, root_data)
        print("\nДля установки запустите: api merge-deps --install")
        print("Для переустановки:      api merge-deps --reinstall")
        return 0

    # ------------------------------------------------------------------ #
    # Project root detection                                               #
    # ------------------------------------------------------------------ #

    def _find_project_root(self) -> Optional[Path]:
        candidates = [
            Path(os.getcwd()),
            # core/api/commands/merge_deps.py → up 4 levels → project root
            Path(__file__).resolve().parent.parent.parent.parent,
        ]
        for candidate in candidates:
            if (candidate / "pyproject.toml").exists():
                return candidate
        return None

    # ------------------------------------------------------------------ #
    # TOML helpers                                                         #
    # ------------------------------------------------------------------ #

    def _read_toml(self, path: Path) -> Optional[dict]:
        try:
            with open(path, "rb") as f:
                return tomllib.load(f)
        except Exception as exc:
            print(f"Ошибка чтения {path}: {exc}")
            return None

    def _get_poetry_deps(self, data: dict) -> dict:
        return data.get("tool", {}).get("poetry", {}).get("dependencies", {})

    # ------------------------------------------------------------------ #
    # Module scanning                                                      #
    # ------------------------------------------------------------------ #

    def _scan_module_configs(
        self, project_root: Path
    ) -> List[Tuple[str, dict]]:
        """Возвращает [(module_name, deps_dict), ...] для всех модулей."""
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

    # ------------------------------------------------------------------ #
    # Dependency merging                                                   #
    # ------------------------------------------------------------------ #

    def _merge_dependencies(
        self,
        root_data: dict,
        module_configs: List[Tuple[str, dict]],
    ) -> Tuple[dict, dict]:
        """
        Сливает зависимости root + всех модулей.
        Возвращает (merged_deps, conflicts), где conflicts — пакеты с
        разными ограничениями в разных источниках.
        """
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
        """Выбирает более строгое (с бо́льшим минимумом) ограничение."""
        if isinstance(a, dict) and not isinstance(b, dict):
            return a
        if isinstance(b, dict) and not isinstance(a, dict):
            return b
        try:
            return a if self._lower_ver(str(a)) >= self._lower_ver(str(b)) else b
        except Exception:
            return a

    def _lower_ver(self, constraint: str) -> tuple:
        """Извлекает первую найденную версию как кортеж чисел."""
        m = re.search(r"(\d+)(?:\.(\d+))?(?:\.(\d+))?", constraint)
        if m:
            return tuple(int(x or 0) for x in m.groups())
        return (0, 0, 0)

    # ------------------------------------------------------------------ #
    # Reporting                                                            #
    # ------------------------------------------------------------------ #

    def _print_merged_deps(self, merged_deps: dict, root_data: dict) -> None:
        root_deps = self._get_poetry_deps(root_data)
        new_pkgs = {k: v for k, v in merged_deps.items() if k not in root_deps}

        print("\n=== Зависимости из модулей (отсутствующие в корне) ===")
        if new_pkgs:
            for pkg, constraint in sorted(new_pkgs.items()):
                print(f"  + {pkg} = {constraint}")
        else:
            print("  (нет новых — все уже есть в корневом pyproject.toml)")

        print(f"\nВсего: {len(merged_deps)} зависимостей, новых из модулей: {len(new_pkgs)}")

    # ------------------------------------------------------------------ #
    # Installation via Poetry                                              #
    # ------------------------------------------------------------------ #

    def _install_missing(
        self, project_root: Path, root_data: dict, merged_deps: dict, force: bool = False
    ) -> int:
        """
        Создаёт временный pyproject.toml с объединёнными зависимостями и
        запускает `poetry install --no-root` с POETRY_VIRTUALENVS_CREATE=false,
        чтобы установка шла в уже активный venv без его пересоздания.

        При force=True сначала удаляет модульные пакеты из venv, затем ставит заново.
        """
        root_deps = self._get_poetry_deps(root_data)
        missing = {
            pkg: constraint
            for pkg, constraint in merged_deps.items()
            if pkg != "python" and pkg not in root_deps
        }

        if not missing:
            print("Все зависимости модулей уже присутствуют в корневом pyproject.toml.")
            return 0

        if force:
            rc = self._uninstall_packages(list(missing.keys()))
            if rc != 0:
                return rc

        print(f"Установка {len(missing)} пакетов через poetry: {', '.join(sorted(missing))}")

        tmp_dir = Path(tempfile.mkdtemp(prefix="ergo_merge_deps_"))
        try:
            toml_content = self._build_merged_toml(root_data, merged_deps, project_root)
            (tmp_dir / "pyproject.toml").write_text(toml_content, encoding="utf-8")

            # Копируем lock-файл: Poetry обновит его только для новых пакетов
            lock_src = project_root / "poetry.lock"
            if lock_src.exists():
                shutil.copy2(lock_src, tmp_dir / "poetry.lock")

            env = os.environ.copy()
            # Не создавать новый venv — использовать текущий активный
            env["POETRY_VIRTUALENVS_CREATE"] = "false"

            # Обновляем lock-файл для новых пакетов (Poetry 2.x сохраняет уже залоченные версии)
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

    def _uninstall_packages(self, packages: List[str]) -> int:
        """Удаляет пакеты из активного venv через pip uninstall."""
        print(f"Удаление {len(packages)} пакетов: {', '.join(sorted(packages))}")
        result = subprocess.run(
            [sys.executable, "-m", "pip", "uninstall", "-y", *packages],
        )
        if result.returncode != 0:
            print("Предупреждение: некоторые пакеты не удалось удалить.")
        return result.returncode

    # ------------------------------------------------------------------ #
    # Merged pyproject.toml builder                                        #
    # ------------------------------------------------------------------ #

    def _build_merged_toml(
        self, root_data: dict, merged_deps: dict, project_root: Path
    ) -> str:
        """
        Генерирует содержимое объединённого pyproject.toml.
        Path-зависимости преобразуются в абсолютные пути, чтобы
        Poetry мог их разрешить из временной директории.
        """
        poetry_section = root_data.get("tool", {}).get("poetry", {})
        sources: list = poetry_section.get("source", [])
        build_system: dict = root_data.get("build-system", {})

        lines: List[str] = []

        lines.append("[tool.poetry]")
        for key in ("name", "version", "description"):
            if key in poetry_section:
                lines.append(f'{key} = "{poetry_section[key]}"')
        lines.append("")

        for source in sources:
            lines.append("[[tool.poetry.source]]")
            for k, v in source.items():
                lines.append(f'{k} = "{v}"')
            lines.append("")

        lines.append("[tool.poetry.dependencies]")
        python_constraint = merged_deps.get("python", ">=3.12,<3.13")
        lines.append(f'python = "{python_constraint}"')
        for pkg, constraint in sorted(merged_deps.items()):
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
        """Сериализует ограничение версии в строку TOML."""
        if isinstance(constraint, str):
            return f'"{constraint}"'
        if isinstance(constraint, dict):
            parts: List[str] = []
            for k, v in constraint.items():
                if k == "path":
                    # Абсолютный путь, чтобы работало из temp-директории
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
