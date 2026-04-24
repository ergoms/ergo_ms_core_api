"""
AST-линтер, запрещающий прямые импорты между модулями.

Правила:
- Файл внутри modules/<X>/... не может импортировать `from modules.<Y> ...`
  или `import modules.<Y>` для Y != X.
- Разрешены:
  * импорты внутри своего модуля (modules/<X>/**);
  * импорты ядра (src.core.*, django.*, rest_framework.*);
  * миграции (modules/<X>/**/migrations/**) — ForeignKey через строковое имя.
- Тесты (modules/<X>/**/tests/**) проверяются по тем же правилам, но допускаются
  импорты `modules.<Y>.api.models` как soft-dep через FK (чтобы не плодить фикстуры).

Для каждого нарушения выводится файл, строка и рекомендуемая замена — bridge.call.
"""

from __future__ import annotations

import ast
import os
from pathlib import Path
from typing import Iterable, Iterator

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError

from src.core.integrations.isolation import (
    ALLOWED_MODULE_PREFIXES as ALLOWED_PREFIXES,
    find_modules_dir,
)


class _Violation:
    __slots__ = ('file', 'line', 'statement', 'foreign_module')

    def __init__(self, file: str, line: int, statement: str, foreign_module: str):
        self.file = file
        self.line = line
        self.statement = statement
        self.foreign_module = foreign_module

    def format(self) -> str:
        return (
            f'{self.file}:{self.line}: {self.statement}'
            f'  (use bridge.call("{self.foreign_module}.<operation>", ...) instead)'
        )


class Command(BaseCommand):
    help = (
        'Проверяет изоляцию модулей: запрещает прямые импорты из чужих '
        '`modules.<X>` вне собственного модуля.'
    )

    def add_arguments(self, parser):
        parser.add_argument(
            '--fail-on-warning',
            action='store_true',
            help='Выходить с ненулевым кодом при наличии нарушений.',
        )
        parser.add_argument(
            '--path',
            default=None,
            help='Проверить только указанную папку/файл (по умолчанию: все модули).',
        )

    def handle(self, *args, **options):
        root = Path(settings.BASE_DIR).resolve()
        scan_path = options.get('path')
        targets, modules_dir = self._resolve_targets(root, scan_path)
        project_root = modules_dir.parent

        violations: list[_Violation] = []
        for py_file, owner in targets:
            violations.extend(self._check_file(py_file, owner, project_root))

        if not violations:
            self.stdout.write(self.style.SUCCESS('Нарушений изоляции модулей не найдено.'))
            return

        self.stdout.write(self.style.WARNING(f'Обнаружено нарушений: {len(violations)}'))
        for v in violations:
            self.stdout.write(self.style.ERROR(v.format()))

        if options.get('fail_on_warning'):
            raise CommandError('Обнаружены нарушения изоляции модулей.')

    def _resolve_targets(
        self,
        root: Path,
        scan_path: str | None,
    ) -> tuple[list[tuple[Path, str]], Path]:
        modules_dir = find_modules_dir(root)
        if modules_dir is None:
            raise CommandError('Не найдена корневая папка modules/.')

        pairs: list[tuple[Path, str]] = []
        if scan_path:
            scan_abs = self._resolve_scan_path(scan_path, root, modules_dir)
            for py in self._iter_python_files(scan_abs):
                owner = self._detect_owner_module(py, modules_dir)
                if owner is not None:
                    pairs.append((py, owner))
            return pairs, modules_dir

        for module_dir in modules_dir.iterdir():
            if not module_dir.is_dir():
                continue
            owner = module_dir.name
            for py in self._iter_python_files(module_dir):
                pairs.append((py, owner))
        return pairs, modules_dir

    @staticmethod
    def _resolve_scan_path(scan_path: str, root: Path, modules_dir: Path) -> Path:
        if os.path.isabs(scan_path):
            return Path(scan_path)
        project_root = modules_dir.parent
        for base in (project_root, root):
            candidate = (base / scan_path).resolve()
            if candidate.exists():
                return candidate
        return (project_root / scan_path).resolve()

    @staticmethod
    def _iter_python_files(start: Path) -> Iterator[Path]:
        if start.is_file() and start.suffix == '.py':
            yield start
            return
        if not start.exists():
            return
        for path in start.rglob('*.py'):
            parts = set(path.parts)
            if '__pycache__' in parts or 'migrations' in parts:
                continue
            yield path

    @staticmethod
    def _detect_owner_module(py: Path, modules_dir: Path) -> str | None:
        try:
            relative = py.resolve().relative_to(modules_dir.resolve())
        except ValueError:
            return None
        parts = relative.parts
        return parts[0] if parts else None

    def _check_file(
        self,
        py: Path,
        owner: str,
        root: Path,
    ) -> Iterable[_Violation]:
        try:
            source = py.read_text(encoding='utf-8')
        except (OSError, UnicodeDecodeError):
            return []

        try:
            tree = ast.parse(source, filename=str(py))
        except SyntaxError:
            return []

        violations: list[_Violation] = []
        rel = str(py.resolve().relative_to(root.resolve())) if py.is_absolute() else str(py)

        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom):
                module = node.module or ''
                foreign = self._extract_foreign_module(module, owner)
                if foreign:
                    violations.append(_Violation(
                        file=rel,
                        line=node.lineno,
                        statement=f'from {module} import ...',
                        foreign_module=foreign,
                    ))
            elif isinstance(node, ast.Import):
                for alias in node.names:
                    foreign = self._extract_foreign_module(alias.name, owner)
                    if foreign:
                        violations.append(_Violation(
                            file=rel,
                            line=node.lineno,
                            statement=f'import {alias.name}',
                            foreign_module=foreign,
                        ))
        return violations

    @staticmethod
    def _extract_foreign_module(import_path: str, owner: str) -> str | None:
        if not import_path:
            return None
        if any(import_path.startswith(p) for p in ALLOWED_PREFIXES):
            return None

        parts = import_path.split('.')
        if not parts or parts[0] != 'modules':
            return None
        if len(parts) < 2:
            return None
        target = parts[1]
        if target == owner:
            return None
        return target
