from __future__ import annotations

import ast
import json
import re
import sys
import tokenize
import tomllib

from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError, CommandParser


SKIP_DIR_NAMES = {
    "__pycache__",
    ".git",
    ".hg",
    ".svn",
    ".mypy_cache",
    ".pytest_cache",
    "node_modules",
    "virtual_env",
    "venv",
    ".venv",
    "build",
    "dist",
}

IMPORT_PACKAGE_MAP = {
    "yaml": "pyyaml",
    "pil": "pillow",
    "cv2": "opencv-python",
    "sklearn": "scikit-learn",
    "rest_framework": "djangorestframework",
    "rest_framework_simplejwt": "djangorestframework-simplejwt",
    "slugify": "python-slugify",
    "environ": "django-environ",
    "bs4": "beautifulsoup4",
    "skimage": "scikit-image",
    "fitz": "pymupdf",
    "faiss": "faiss-cpu",
}

REQ_NAME_RE = re.compile(r"^\s*([A-Za-z0-9][A-Za-z0-9._-]*)")
NORMALIZE_RE = re.compile(r"[-_.]+")


@dataclass
class ParseErrorItem:
    file: str
    message: str


@dataclass
class ScopeReport:
    name: str
    path: Path
    python_files: int = 0
    all_imports: set[str] = field(default_factory=set)
    stdlib_imports: set[str] = field(default_factory=set)
    local_imports: set[str] = field(default_factory=set)
    external_imports: set[str] = field(default_factory=set)
    parse_errors: list[ParseErrorItem] = field(default_factory=list)
    pyproject_path: Path | None = None
    declared_dependencies: set[str] = field(default_factory=set)
    used_dependencies: set[str] = field(default_factory=set)
    used_not_declared: set[str] = field(default_factory=set)
    declared_not_used: set[str] = field(default_factory=set)
    dependency_compare_error: str | None = None


def normalize_dependency_name(value: str) -> str:
    return NORMALIZE_RE.sub("-", value).strip("-").lower()


def map_import_to_dependency(import_name: str) -> str:
    mapped = IMPORT_PACKAGE_MAP.get(import_name.lower(), import_name)
    return normalize_dependency_name(mapped)


def parse_requirement_name(requirement: str) -> str | None:
    match = REQ_NAME_RE.match(requirement)
    if not match:
        return None
    return match.group(1)


def load_declared_dependencies(pyproject_path: Path) -> set[str]:
    with pyproject_path.open("rb") as file_obj:
        data = tomllib.load(file_obj)

    dependencies: set[str] = set()

    tool_data = data.get("tool", {})
    poetry_data = tool_data.get("poetry", {}) if isinstance(tool_data, dict) else {}
    poetry_deps = poetry_data.get("dependencies", {}) if isinstance(poetry_data, dict) else {}
    if isinstance(poetry_deps, dict):
        for dep_name in poetry_deps:
            normalized = normalize_dependency_name(dep_name)
            if normalized and normalized != "python":
                dependencies.add(normalized)

    poetry_groups = poetry_data.get("group", {}) if isinstance(poetry_data, dict) else {}
    if isinstance(poetry_groups, dict):
        for group_config in poetry_groups.values():
            if not isinstance(group_config, dict):
                continue
            group_deps = group_config.get("dependencies", {})
            if not isinstance(group_deps, dict):
                continue
            for dep_name in group_deps:
                normalized = normalize_dependency_name(dep_name)
                if normalized and normalized != "python":
                    dependencies.add(normalized)

    project_data = data.get("project", {})
    if isinstance(project_data, dict):
        project_deps = project_data.get("dependencies", [])
        if isinstance(project_deps, list):
            for requirement in project_deps:
                if not isinstance(requirement, str):
                    continue
                dep_name = parse_requirement_name(requirement)
                if not dep_name:
                    continue
                normalized = normalize_dependency_name(dep_name)
                if normalized and normalized != "python":
                    dependencies.add(normalized)

        optional_data = project_data.get("optional-dependencies", {})
        if isinstance(optional_data, dict):
            for optional_reqs in optional_data.values():
                if not isinstance(optional_reqs, list):
                    continue
                for requirement in optional_reqs:
                    if not isinstance(requirement, str):
                        continue
                    dep_name = parse_requirement_name(requirement)
                    if not dep_name:
                        continue
                    normalized = normalize_dependency_name(dep_name)
                    if normalized and normalized != "python":
                        dependencies.add(normalized)

    return dependencies


def detect_project_root(provided_root: str | None) -> Path:
    if provided_root:
        root = Path(provided_root).expanduser().resolve()
        if not root.is_dir():
            raise CommandError(f"Provided root path does not exist: {root}")
        return root

    settings_root = getattr(settings, "SYSTEM_DIR", None)
    if settings_root:
        root = Path(settings_root).resolve()
        if root.is_dir():
            return root

    current = Path(__file__).resolve()
    for parent in current.parents:
        if (parent / "core" / "api" / "src").is_dir() and (parent / "modules").is_dir():
            return parent

    raise CommandError("Failed to detect project root")


def detect_core_path(project_root: Path) -> Path:
    candidates = (
        project_root / "core" / "api" / "src",
        project_root / "core" / "api",
    )
    for candidate in candidates:
        if candidate.is_dir():
            return candidate
    raise CommandError("Failed to detect core path")


def find_core_pyproject(project_root: Path, core_path: Path) -> Path | None:
    root_pyproject = project_root / "pyproject.toml"
    if root_pyproject.is_file():
        return root_pyproject

    for parent in (core_path, *core_path.parents):
        candidate = parent / "pyproject.toml"
        if candidate.is_file():
            return candidate
        if parent == project_root:
            break

    return None


def iter_module_dirs(modules_path: Path) -> Iterable[Path]:
    for module_dir in sorted(modules_path.iterdir(), key=lambda path_obj: path_obj.name.lower()):
        if not module_dir.is_dir():
            continue
        if module_dir.name.startswith("."):
            continue
        if module_dir.name.lower() in SKIP_DIR_NAMES:
            continue
        yield module_dir


def build_local_import_names(core_path: Path, modules_path: Path) -> set[str]:
    names = {"src", "modules", "commands"}

    for child in core_path.iterdir():
        if not child.is_dir():
            continue
        if child.name.startswith("."):
            continue
        if child.name.lower() in SKIP_DIR_NAMES:
            continue
        names.add(child.name)

    for module_dir in iter_module_dirs(modules_path):
        names.add(module_dir.name)

    return names


def iter_python_files(root_path: Path) -> Iterable[Path]:
    stack = [root_path]

    while stack:
        current = stack.pop()

        try:
            children = sorted(current.iterdir(), key=lambda path_obj: path_obj.name.lower())
        except OSError:
            continue

        for child in children:
            name_lower = child.name.lower()
            if child.is_dir():
                if name_lower in SKIP_DIR_NAMES:
                    continue
                stack.append(child)
                continue

            if child.suffix == ".py":
                yield child


def extract_top_level_imports(tree: ast.AST) -> set[str]:
    imports: set[str] = set()

    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                name = alias.name.split(".", 1)[0]
                if name:
                    imports.add(name)
        elif isinstance(node, ast.ImportFrom):
            if node.level != 0:
                continue
            if not node.module:
                continue
            name = node.module.split(".", 1)[0]
            if name:
                imports.add(name)

    return imports


def scan_scope(
    *,
    name: str,
    scope_path: Path,
    project_root: Path,
    local_import_names: set[str],
    stdlib_names: set[str],
    pyproject_path: Path | None,
) -> ScopeReport:
    report = ScopeReport(name=name, path=scope_path, pyproject_path=pyproject_path)
    local_names_lower = {name_item.lower() for name_item in local_import_names}
    stdlib_names_lower = {name_item.lower() for name_item in stdlib_names}

    for file_path in iter_python_files(scope_path):
        report.python_files += 1
        rel_file = str(file_path.relative_to(project_root))

        try:
            with tokenize.open(file_path) as file_obj:
                source = file_obj.read()
            tree = ast.parse(source, filename=rel_file)
        except (OSError, SyntaxError, UnicodeDecodeError) as exc:
            report.parse_errors.append(ParseErrorItem(file=rel_file, message=str(exc)))
            continue

        report.all_imports.update(extract_top_level_imports(tree))

    for import_name in report.all_imports:
        normalized_name = import_name.lower()
        if normalized_name in stdlib_names_lower:
            report.stdlib_imports.add(import_name)
        elif normalized_name in local_names_lower:
            report.local_imports.add(import_name)
        else:
            report.external_imports.add(import_name)

    report.used_dependencies = set()
    for import_name in report.external_imports:
        mapped = map_import_to_dependency(import_name)
        if mapped:
            report.used_dependencies.add(mapped)

    if pyproject_path and pyproject_path.is_file():
        try:
            report.declared_dependencies = load_declared_dependencies(pyproject_path)
            report.used_not_declared = report.used_dependencies - report.declared_dependencies
            report.declared_not_used = report.declared_dependencies - report.used_dependencies
        except Exception as exc:
            report.dependency_compare_error = str(exc)

    return report


def build_json_payload(
    *,
    project_root: Path,
    core_path: Path,
    modules_path: Path,
    reports: list[ScopeReport],
) -> dict:
    return {
        "project_root": str(project_root),
        "core_path": str(core_path),
        "modules_path": str(modules_path),
        "reports": [
            {
                "name": report.name,
                "path": str(report.path),
                "python_files": report.python_files,
                "stdlib_imports": sorted(report.stdlib_imports),
                "local_imports": sorted(report.local_imports),
                "external_imports": sorted(report.external_imports),
                "used_dependencies": sorted(report.used_dependencies),
                "declared_dependencies": sorted(report.declared_dependencies),
                "used_not_declared": sorted(report.used_not_declared),
                "declared_not_used": sorted(report.declared_not_used),
                "parse_errors": [
                    {"file": parse_error.file, "message": parse_error.message}
                    for parse_error in report.parse_errors
                ],
                "pyproject": str(report.pyproject_path) if report.pyproject_path else None,
                "dependency_compare_error": report.dependency_compare_error,
            }
            for report in reports
        ],
    }


class Command(BaseCommand):
    help = "Scan imports in core/modules and compare external usage with declared dependencies."

    def add_arguments(self, parser: CommandParser) -> None:
        parser.add_argument(
            "action",
            nargs="?",
            default="scan",
            choices=["scan"],
            help="Only 'scan' is supported in the current version.",
        )
        parser.add_argument(
            "--root",
            dest="root",
            default=None,
            help="Project root path. Auto-detected by default.",
        )
        parser.add_argument(
            "--json",
            dest="as_json",
            action="store_true",
            help="Print report as JSON.",
        )

    def handle(self, *args: tuple, **options: dict) -> None:
        _ = options["action"]

        project_root = detect_project_root(options.get("root"))
        core_path = detect_core_path(project_root)
        modules_path = project_root / "modules"
        if not modules_path.is_dir():
            raise CommandError(f"Modules directory not found: {modules_path}")

        local_import_names = build_local_import_names(core_path, modules_path)
        stdlib_names = set(sys.builtin_module_names)
        stdlib_names.update(getattr(sys, "stdlib_module_names", set()))

        reports: list[ScopeReport] = []

        reports.append(
            scan_scope(
                name="core",
                scope_path=core_path,
                project_root=project_root,
                local_import_names=local_import_names,
                stdlib_names=stdlib_names,
                pyproject_path=find_core_pyproject(project_root, core_path),
            )
        )

        for module_dir in iter_module_dirs(modules_path):
            module_pyproject = module_dir / "pyproject.toml"
            reports.append(
                scan_scope(
                    name=f"module:{module_dir.name}",
                    scope_path=module_dir,
                    project_root=project_root,
                    local_import_names=local_import_names,
                    stdlib_names=stdlib_names,
                    pyproject_path=module_pyproject if module_pyproject.is_file() else None,
                )
            )

        if options.get("as_json"):
            payload = build_json_payload(
                project_root=project_root,
                core_path=core_path,
                modules_path=modules_path,
                reports=reports,
            )
            self.stdout.write(json.dumps(payload, indent=2, sort_keys=True))
            return

        self._print_human_report(
            project_root=project_root,
            core_path=core_path,
            modules_path=modules_path,
            reports=reports,
        )

    def _print_human_report(
        self,
        *,
        project_root: Path,
        core_path: Path,
        modules_path: Path,
        reports: list[ScopeReport],
    ) -> None:
        self.stdout.write("Dependency scan report")
        self.stdout.write("======================")
        self.stdout.write(f"project root: {project_root}")
        self.stdout.write(f"core path:    {core_path}")
        self.stdout.write(f"modules path: {modules_path}")

        for report in reports:
            self.stdout.write("")
            self.stdout.write(f"[{report.name}]")
            self.stdout.write(f"  path: {report.path}")
            self.stdout.write(f"  python files: {report.python_files}")
            self.stdout.write(
                "  imports: "
                f"stdlib={len(report.stdlib_imports)}, "
                f"local={len(report.local_imports)}, "
                f"external={len(report.external_imports)}"
            )

            self._write_set("external imports", report.external_imports)
            self._write_set("used dependencies", report.used_dependencies)

            if report.pyproject_path:
                self.stdout.write(f"  pyproject: {report.pyproject_path}")
                if report.dependency_compare_error:
                    self.stdout.write(
                        self.style.WARNING(
                            f"  dependency compare error: {report.dependency_compare_error}"
                        )
                    )
                else:
                    self._write_set("used but not declared", report.used_not_declared)
                    self._write_set("declared but not used", report.declared_not_used)
            else:
                self.stdout.write("  pyproject: not found (comparison skipped)")

            if report.parse_errors:
                self.stdout.write(
                    self.style.WARNING(f"  parse errors: {len(report.parse_errors)}")
                )
                for parse_error in report.parse_errors:
                    self.stdout.write(f"    - {parse_error.file}: {parse_error.message}")
            else:
                self.stdout.write("  parse errors: 0")

    def _write_set(self, title: str, values: set[str]) -> None:
        if not values:
            self.stdout.write(f"  {title}: -")
            return
        self.stdout.write(f"  {title} ({len(values)}): {', '.join(sorted(values))}")
