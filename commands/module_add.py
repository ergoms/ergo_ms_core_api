"""
Команда для добавления зависимости в pyproject.toml конкретного модуля.

Использование:
    api module-add <модуль> <пакет>                  — добавить пакет (версия авторазрешается)
    api module-add <модуль> <пакет> "<constraint>"   — добавить с явным ограничением
    api module-add <модуль> <пакет> --install        — добавить и сразу установить
    api module-list                                  — список модулей с pyproject.toml
"""

import os
import re
import subprocess
import sys
import tomllib
from pathlib import Path
from typing import Any, Optional

from commands.base import PoetryCommand


class ModuleAddCommand(PoetryCommand):
    """Добавляет зависимость в pyproject.toml конкретного модуля."""

    poetry_command_name = "module-add"
    script_command = "module-add"

    def run(self, *args) -> int:
        args = [a for a in args if a]

        if not args:
            self._print_usage()
            return 1

        install = "--install" in args
        args = [a for a in args if a != "--install"]

        if len(args) < 2:
            self._print_usage()
            return 1

        module_name = args[0]
        package = args[1]
        constraint = args[2] if len(args) >= 3 else None

        project_root = self._find_project_root()
        if project_root is None:
            print("Ошибка: не удалось найти корневой pyproject.toml.")
            return 1

        module_toml = project_root / "modules" / module_name / "pyproject.toml"
        if not module_toml.exists():
            print(f"Ошибка: модуль '{module_name}' не найден или не имеет pyproject.toml.")
            print(f"  Ожидался файл: {module_toml}")
            self._list_modules(project_root)
            return 1

        if constraint is None:
            constraint = self._resolve_version(package)
            if constraint is None:
                print(f"Не удалось определить версию для '{package}'. Укажите вручную.")
                return 1
            print(f"  Разрешена версия: {package} = \"{constraint}\"")

        rc = self._add_to_toml(module_toml, package, constraint)
        if rc != 0:
            return rc

        print(f"✓ Добавлено в {module_toml.relative_to(project_root)}:")
        print(f"    {package} = \"{constraint}\"")

        if install:
            print("\nЗапуск установки через merge-deps --install...")
            from commands.merge_deps import MergeDepsCommand
            return MergeDepsCommand().run("--install")

        print("\nДля установки запустите: api merge-deps --install")
        return 0

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

    def _resolve_version(self, package: str) -> Optional[str]:
        """Получает последнюю версию пакета через pip index versions."""
        try:
            result = subprocess.run(
                [sys.executable, "-m", "pip", "index", "versions", package],
                capture_output=True,
                text=True,
                timeout=15,
            )
            # pip output: "package (X.Y.Z)"
            match = re.search(r"\(([^)]+)\)", result.stdout)
            if match:
                latest = match.group(1).split(",")[0].strip()
                # Берём major.minor как нижнюю границу
                parts = latest.split(".")
                if len(parts) >= 2:
                    return f">={parts[0]}.{parts[1]}.0"
                return f">={latest}"
        except Exception:
            pass
        return None

    def _add_to_toml(self, toml_path: Path, package: str, constraint: str) -> int:
        """
        Добавляет строку зависимости в [tool.poetry.dependencies].
        Если пакет уже есть — обновляет его версию.
        """
        try:
            text = toml_path.read_text(encoding="utf-8")
        except Exception as e:
            print(f"Ошибка чтения {toml_path}: {e}")
            return 1

        # Проверяем существующую запись
        pkg_pattern = re.compile(
            rf'^{re.escape(package)}\s*=\s*.+$', re.MULTILINE | re.IGNORECASE
        )
        new_line = f'{package} = "{constraint}"'

        if pkg_pattern.search(text):
            # Обновляем существующую
            updated = pkg_pattern.sub(new_line, text)
            print(f"  (обновлена существующая запись)")
        else:
            # Ищем конец секции [tool.poetry.dependencies] через lookahead:
            # останавливаемся перед следующим заголовком (\n[) или концом файла.
            # Это важно: [^\[] прерывался бы на [ внутри inline-таблиц.
            section_pattern = re.compile(
                r'(\[tool\.poetry\.dependencies\].*?)(?=\n\s*\[|\Z)', re.DOTALL
            )
            match = section_pattern.search(text)
            if not match:
                print(f"Ошибка: секция [tool.poetry.dependencies] не найдена в {toml_path}")
                return 1

            section_end = match.end()
            updated = text[:section_end].rstrip() + "\n" + new_line + "\n" + text[section_end:]

        # Верифицируем до записи
        try:
            tomllib.loads(updated)
        except Exception as e:
            print(f"Ошибка: результирующий TOML невалиден: {e}")
            return 1

        try:
            toml_path.write_text(updated, encoding="utf-8")
        except Exception as e:
            print(f"Ошибка записи {toml_path}: {e}")
            return 1

        return 0

    def _list_modules(self, project_root: Path) -> None:
        modules_dir = project_root / "modules"
        if not modules_dir.exists():
            return
        modules = [
            d.name for d in sorted(modules_dir.iterdir())
            if d.is_dir() and (d / "pyproject.toml").exists()
        ]
        print(f"\nМодули с pyproject.toml ({len(modules)}):")
        for m in modules:
            print(f"  • {m}")

    def _print_usage(self) -> None:
        print("Использование:")
        print("  api module-add <модуль> <пакет>                 — авторазрешение версии")
        print('  api module-add <модуль> <пакет> ">=1.0.0"       — явное ограничение')
        print("  api module-add <модуль> <пакет> --install       — добавить и установить")
        print("  api module-list                                  — список модулей")


class ModuleRemoveCommand(PoetryCommand):
    """Удаляет зависимость из pyproject.toml конкретного модуля."""

    poetry_command_name = "module-remove"
    script_command = "module-remove"

    def run(self, *args) -> int:
        args = [a for a in args if a]

        if len(args) < 2:
            print("Использование:")
            print("  api module-remove <модуль> <пакет>")
            return 1

        module_name = args[0]
        package = args[1]

        project_root = self._find_project_root()
        if project_root is None:
            print("Ошибка: не удалось найти корневой pyproject.toml.")
            return 1

        module_toml = project_root / "modules" / module_name / "pyproject.toml"
        if not module_toml.exists():
            print(f"Ошибка: модуль '{module_name}' не найден или не имеет pyproject.toml.")
            return 1

        return self._remove_from_toml(module_toml, package, project_root)

    def _find_project_root(self) -> Optional[Path]:
        candidates = [
            Path(os.getcwd()),
            Path(__file__).resolve().parent.parent.parent.parent,
        ]
        for c in candidates:
            if (c / "pyproject.toml").exists():
                return c
        return None

    def _remove_from_toml(self, toml_path: Path, package: str, project_root: Path) -> int:
        try:
            text = toml_path.read_text(encoding="utf-8")
        except Exception as e:
            print(f"Ошибка чтения {toml_path}: {e}")
            return 1

        # Ищем строку с пакетом (простая и inline-таблица)
        pkg_pattern = re.compile(
            rf'^{re.escape(package)}\s*=\s*.+\n?', re.MULTILINE | re.IGNORECASE
        )

        if not pkg_pattern.search(text):
            print(f"Пакет '{package}' не найден в {toml_path.relative_to(project_root)}")
            return 1

        updated = pkg_pattern.sub("", text)

        # Убираем возможные двойные пустые строки
        updated = re.sub(r'\n{3,}', '\n\n', updated)

        # Верифицируем TOML
        try:
            import tomllib
            tomllib.loads(updated)
        except Exception as e:
            print(f"Ошибка: результирующий TOML невалиден: {e}")
            return 1

        try:
            toml_path.write_text(updated, encoding="utf-8")
        except Exception as e:
            print(f"Ошибка записи {toml_path}: {e}")
            return 1

        print(f"✓ Удалено из {toml_path.relative_to(project_root)}:")
        print(f"    {package}")
        return 0


class ModuleListCommand(PoetryCommand):
    """Показывает список модулей с их pyproject.toml."""

    poetry_command_name = "module-list"
    script_command = "module-list"

    def run(self, *args) -> int:
        candidates = [
            Path(os.getcwd()),
            Path(__file__).resolve().parent.parent.parent.parent,
        ]
        project_root = next((c for c in candidates if (c / "pyproject.toml").exists()), None)
        if project_root is None:
            print("Ошибка: не удалось найти корневой pyproject.toml.")
            return 1

        modules_dir = project_root / "modules"
        if not modules_dir.exists():
            print("Директория modules не найдена.")
            return 1

        print("\nМодули с pyproject.toml:\n")
        found = 0
        for module_dir in sorted(modules_dir.iterdir()):
            if not module_dir.is_dir():
                continue
            toml_path = module_dir / "pyproject.toml"
            if not toml_path.exists():
                continue
            found += 1
            try:
                with open(toml_path, "rb") as f:
                    data = tomllib.load(f)
                deps = data.get("tool", {}).get("poetry", {}).get("dependencies", {})
                pkg_count = len([k for k in deps if k != "python"])
                print(f"  {module_dir.name:<35} ({pkg_count} зависимостей)")
            except Exception:
                print(f"  {module_dir.name:<35} (ошибка чтения)")

        print(f"\nВсего: {found} модулей")
        return 0
