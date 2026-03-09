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

BUILTIN_EXACT_IMPORT_MAP = {
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
    "django_filters": "django-filter",
    "dateutil": "python-dateutil",
}

BUILTIN_AMBIGUOUS_IMPORT_MAP = {
    "mysql": {"mysql-connector-python"},
    "docx": {"docx", "python-docx"},
}

REQ_NAME_RE = re.compile(r"^\s*([A-Za-z0-9][A-Za-z0-9._-]*)")
NORMALIZE_RE = re.compile(r"[-_.]+")


@dataclass
class ParseErrorItem:
    file: str
    message: str


@dataclass
class DepsOverrides:
    import_map: dict[str, str] = field(default_factory=dict)
    ambiguous_map: dict[str, set[str]] = field(default_factory=dict)
    ignore_imports: set[str] = field(default_factory=set)
    ignore_dependencies: set[str] = field(default_factory=set)


@dataclass
class ImportResolution:
    status: str
    dependency: str | None = None
    candidates: set[str] = field(default_factory=set)


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
    used_dependencies: set[str] = field(default_factory=set)
    indirect_in_shared: set[str] = field(default_factory=set)
    missing_in_shared: set[str] = field(default_factory=set)
    ambiguous_imports: dict[str, set[str]] = field(default_factory=dict)
    unresolved_imports: set[str] = field(default_factory=set)


@dataclass
class WorkspaceAmbiguousImport:
    candidates: set[str] = field(default_factory=set)
    scopes: set[str] = field(default_factory=set)


@dataclass
class WorkspaceReport:
    shared_pyproject_path: Path | None
    comparison_available: bool = False
    declared_shared: set[str] = field(default_factory=set)
    workspace_used: set[str] = field(default_factory=set)
    unused_in_shared: set[str] = field(default_factory=set)
    dependency_scopes: dict[str, set[str]] = field(default_factory=dict)
    shared_dependencies: set[str] = field(default_factory=set)
    exclusive_dependencies_by_scope: dict[str, set[str]] = field(default_factory=dict)
    workspace_indirect_dependencies: set[str] = field(default_factory=set)
    workspace_ambiguous_imports: dict[str, WorkspaceAmbiguousImport] = field(
        default_factory=dict
    )
    workspace_unresolved_imports: set[str] = field(default_factory=set)
    ignored_dependencies: set[str] = field(default_factory=set)
    dependency_compare_error: str | None = None


@dataclass
class ScanSummary:
    scopes_scanned: int
    total_parse_errors: int
    total_missing_in_shared: int
    total_unused_in_shared: int


def normalize_dependency_name(value: str) -> str:
    return NORMALIZE_RE.sub("-", value).strip("-").lower()


def parse_requirement_name(requirement: str) -> str | None:
    match = REQ_NAME_RE.match(requirement)
    if not match:
        return None
    return match.group(1)


def load_toml(path: Path) -> dict:
    with path.open("rb") as file_obj:
        data = tomllib.load(file_obj)
    if not isinstance(data, dict):
        raise ValueError(f"Invalid TOML root object in {path}")
    return data


def extract_declared_dependencies(pyproject_data: dict) -> set[str]:
    dependencies: set[str] = set()

    tool_data = pyproject_data.get("tool", {})
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

    project_data = pyproject_data.get("project", {})
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

def extract_deps_overrides(pyproject_data: dict) -> DepsOverrides:
    tool_data = pyproject_data.get("tool", {})
    if not isinstance(tool_data, dict):
        return DepsOverrides()

    ergoms_data = tool_data.get("ergoms", {})
    if not isinstance(ergoms_data, dict):
        return DepsOverrides()

    deps_data = ergoms_data.get("deps", {})
    if not isinstance(deps_data, dict):
        return DepsOverrides()

    import_map: dict[str, str] = {}
    import_map_raw = deps_data.get("import-map", {})
    if isinstance(import_map_raw, dict):
        for import_name, dep_name in import_map_raw.items():
            if not isinstance(import_name, str) or not isinstance(dep_name, str):
                continue
            normalized_dep = normalize_dependency_name(dep_name)
            if normalized_dep:
                import_map[import_name.lower()] = normalized_dep

    ambiguous_map: dict[str, set[str]] = {}
    ambiguous_map_raw = deps_data.get("ambiguous-map", {})
    if isinstance(ambiguous_map_raw, dict):
        for import_name, candidates in ambiguous_map_raw.items():
            if not isinstance(import_name, str) or not isinstance(candidates, list):
                continue
            normalized_candidates = {
                normalize_dependency_name(candidate)
                for candidate in candidates
                if isinstance(candidate, str)
            }
            normalized_candidates.discard("")
            if normalized_candidates:
                ambiguous_map[import_name.lower()] = normalized_candidates

    ignore_imports: set[str] = set()
    ignore_imports_raw = deps_data.get("ignore-imports", [])
    if isinstance(ignore_imports_raw, list):
        ignore_imports = {
            value.lower().strip()
            for value in ignore_imports_raw
            if isinstance(value, str) and value.strip()
        }

    ignore_dependencies: set[str] = set()
    ignore_dependencies_raw = deps_data.get("ignore-dependencies", [])
    if isinstance(ignore_dependencies_raw, list):
        ignore_dependencies = {
            normalize_dependency_name(value)
            for value in ignore_dependencies_raw
            if isinstance(value, str)
        }
        ignore_dependencies.discard("")

    return DepsOverrides(
        import_map=import_map,
        ambiguous_map=ambiguous_map,
        ignore_imports=ignore_imports,
        ignore_dependencies=ignore_dependencies,
    )


def build_resolver_maps(
    overrides: DepsOverrides,
) -> tuple[dict[str, str], dict[str, set[str]]]:
    exact_map = {
        key.lower(): normalize_dependency_name(value)
        for key, value in BUILTIN_EXACT_IMPORT_MAP.items()
    }
    ambiguous_map = {
        key.lower(): {normalize_dependency_name(candidate) for candidate in candidates}
        for key, candidates in BUILTIN_AMBIGUOUS_IMPORT_MAP.items()
    }

    for key in overrides.ambiguous_map:
        exact_map.pop(key, None)
    for key in overrides.import_map:
        ambiguous_map.pop(key, None)

    exact_map.update(overrides.import_map)
    for key, candidates in overrides.ambiguous_map.items():
        ambiguous_map[key] = set(candidates)

    exact_map = {key: value for key, value in exact_map.items() if value}
    ambiguous_map = {
        key: {candidate for candidate in candidates if candidate}
        for key, candidates in ambiguous_map.items()
        if candidates
    }

    return exact_map, ambiguous_map


def resolve_import_dependency(
    import_name: str,
    *,
    exact_map: dict[str, str],
    ambiguous_map: dict[str, set[str]],
) -> ImportResolution:
    key = import_name.lower().strip()
    if not key:
        return ImportResolution(status="unresolved")

    if key in exact_map:
        return ImportResolution(status="resolved", dependency=exact_map[key])

    if key in ambiguous_map:
        return ImportResolution(status="ambiguous", candidates=set(ambiguous_map[key]))

    if key.startswith("django_"):
        fallback_dep = normalize_dependency_name(key.replace("_", "-"))
        if fallback_dep:
            return ImportResolution(status="resolved", dependency=fallback_dep)

    fallback_dep = normalize_dependency_name(key)
    if fallback_dep:
        return ImportResolution(status="resolved", dependency=fallback_dep)

    return ImportResolution(status="unresolved")


def load_poetry_dependency_graph(lock_path: Path) -> dict[str, set[str]]:
    lock_data = load_toml(lock_path)
    package_entries = lock_data.get("package", [])
    if not isinstance(package_entries, list):
        raise ValueError("'package' section must be a list")

    graph: dict[str, set[str]] = {}

    for package_data in package_entries:
        if not isinstance(package_data, dict):
            continue
        package_name = package_data.get("name")
        if not isinstance(package_name, str):
            continue

        package_key = normalize_dependency_name(package_name)
        if not package_key:
            continue

        graph.setdefault(package_key, set())
        package_dependencies = package_data.get("dependencies", {})
        if not isinstance(package_dependencies, dict):
            continue

        for dependency_name in package_dependencies:
            if not isinstance(dependency_name, str):
                continue
            dependency_key = normalize_dependency_name(dependency_name)
            if not dependency_key or dependency_key == "python":
                continue
            graph[package_key].add(dependency_key)

    return graph


def compute_transitive_from_declared(
    declared_dependencies: set[str],
    dependency_graph: dict[str, set[str]],
) -> set[str]:
    visited: set[str] = set()
    transitive: set[str] = set()
    stack = list(declared_dependencies)

    while stack:
        current = stack.pop()
        if current in visited:
            continue
        visited.add(current)

        for dependency in dependency_graph.get(current, set()):
            if dependency not in visited:
                stack.append(dependency)
            transitive.add(dependency)

    return transitive - declared_dependencies


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


def find_shared_pyproject(project_root: Path) -> Path | None:
    pyproject_path = project_root / "pyproject.toml"
    if pyproject_path.is_file():
        return pyproject_path
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


def is_probably_import_root(path_obj: Path) -> bool:
    if not path_obj.is_dir():
        return False

    if (path_obj / "__init__.py").is_file():
        return True

    try:
        for child in path_obj.iterdir():
            if child.is_file() and child.suffix == ".py":
                return True
            if child.is_dir() and child.name.lower() not in SKIP_DIR_NAMES:
                if (child / "__init__.py").is_file():
                    return True
    except OSError:
        return False

    return False


def collect_scope_local_import_names(scope_path: Path) -> set[str]:
    names: set[str] = set()

    try:
        children = sorted(scope_path.iterdir(), key=lambda path_obj: path_obj.name.lower())
    except OSError:
        return names

    for child in children:
        if child.is_file() and child.suffix == ".py":
            if not child.stem.startswith("__"):
                names.add(child.stem)
            continue

        if not child.is_dir():
            continue
        if child.name.startswith("."):
            continue
        if child.name.lower() in SKIP_DIR_NAMES:
            continue
        if is_probably_import_root(child):
            names.add(child.name)

    return names


def build_common_local_import_names(modules_path: Path) -> set[str]:
    names = {"src", "modules", "commands", "core"}

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
    exact_map: dict[str, str],
    ambiguous_map: dict[str, set[str]],
    ignore_imports: set[str],
) -> ScopeReport:
    report = ScopeReport(name=name, path=scope_path)
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

    for import_name in report.external_imports:
        import_key = import_name.lower()
        if import_key in ignore_imports:
            continue

        resolution = resolve_import_dependency(
            import_name,
            exact_map=exact_map,
            ambiguous_map=ambiguous_map,
        )
        if resolution.status == "resolved" and resolution.dependency:
            report.used_dependencies.add(resolution.dependency)
        elif resolution.status == "ambiguous":
            report.ambiguous_imports[import_name] = set(resolution.candidates)
        else:
            report.unresolved_imports.add(import_name)

    return report


def build_workspace_report(
    *,
    reports: list[ScopeReport],
    shared_pyproject_path: Path | None,
    comparison_available: bool,
    declared_shared: set[str],
    transitive_from_declared: set[str],
    ignore_dependencies: set[str],
    dependency_compare_error: str | None,
) -> WorkspaceReport:
    dependency_scopes: dict[str, set[str]] = {}
    for report in reports:
        for dep in report.used_dependencies:
            dependency_scopes.setdefault(dep, set()).add(report.name)

    workspace_used = set(dependency_scopes)

    shared_dependencies: set[str] = set()
    exclusive_dependencies_by_scope: dict[str, set[str]] = {}
    for dep, scopes in dependency_scopes.items():
        if len(scopes) >= 2:
            shared_dependencies.add(dep)
            continue
        scope_name = next(iter(scopes))
        exclusive_dependencies_by_scope.setdefault(scope_name, set()).add(dep)

    for report in reports:
        exclusive_dependencies_by_scope.setdefault(report.name, set())

    workspace_ambiguous_imports: dict[str, WorkspaceAmbiguousImport] = {}
    workspace_unresolved_imports: set[str] = set()
    for report in reports:
        for import_name, candidates in report.ambiguous_imports.items():
            import_key = import_name.lower()
            item = workspace_ambiguous_imports.setdefault(
                import_key,
                WorkspaceAmbiguousImport(),
            )
            item.candidates.update(candidates)
            item.scopes.add(report.name)

        workspace_unresolved_imports.update(
            import_name.lower() for import_name in report.unresolved_imports
        )

    workspace_indirect_dependencies: set[str] = set()
    if comparison_available:
        effective_declared_shared = declared_shared - ignore_dependencies
        effective_transitive = transitive_from_declared - ignore_dependencies
        effective_transitive -= effective_declared_shared

        workspace_used_for_compare: set[str] = set()
        for report in reports:
            used_for_compare = report.used_dependencies - ignore_dependencies
            report.indirect_in_shared = used_for_compare & effective_transitive
            report.missing_in_shared = (
                used_for_compare - effective_declared_shared - report.indirect_in_shared
            )
            workspace_indirect_dependencies.update(report.indirect_in_shared)
            workspace_used_for_compare.update(used_for_compare)

        unused_in_shared = effective_declared_shared - workspace_used_for_compare
    else:
        for report in reports:
            report.indirect_in_shared = set()
            report.missing_in_shared = set()
        unused_in_shared = set()

    return WorkspaceReport(
        shared_pyproject_path=shared_pyproject_path,
        comparison_available=comparison_available,
        declared_shared=declared_shared,
        workspace_used=workspace_used,
        unused_in_shared=unused_in_shared,
        dependency_scopes=dependency_scopes,
        shared_dependencies=shared_dependencies,
        exclusive_dependencies_by_scope=exclusive_dependencies_by_scope,
        workspace_indirect_dependencies=workspace_indirect_dependencies,
        workspace_ambiguous_imports=workspace_ambiguous_imports,
        workspace_unresolved_imports=workspace_unresolved_imports,
        ignored_dependencies=set(ignore_dependencies),
        dependency_compare_error=dependency_compare_error,
    )


def build_summary(reports: list[ScopeReport], workspace: WorkspaceReport) -> ScanSummary:
    return ScanSummary(
        scopes_scanned=len(reports),
        total_parse_errors=sum(len(report.parse_errors) for report in reports),
        total_missing_in_shared=sum(len(report.missing_in_shared) for report in reports),
        total_unused_in_shared=len(workspace.unused_in_shared),
    )


def evaluate_strict_exit_code(
    summary: ScanSummary, *, fail_on_declared_not_used: bool
) -> int:
    if summary.total_parse_errors > 0:
        return 1
    if summary.total_missing_in_shared > 0:
        return 2
    if fail_on_declared_not_used and summary.total_unused_in_shared > 0:
        return 3
    return 0


def build_json_payload(
    *,
    project_root: Path,
    core_path: Path,
    modules_path: Path,
    summary: ScanSummary,
    reports: list[ScopeReport],
    workspace: WorkspaceReport,
) -> dict:
    dependency_scopes_payload = {
        dep: sorted(scopes)
        for dep, scopes in sorted(workspace.dependency_scopes.items(), key=lambda item: item[0])
    }
    exclusive_payload = {
        scope_name: sorted(dependencies)
        for scope_name, dependencies in sorted(
            workspace.exclusive_dependencies_by_scope.items(),
            key=lambda item: item[0].lower(),
        )
    }
    workspace_ambiguous_payload = {
        import_name: {
            "candidates": sorted(item.candidates),
            "scopes": sorted(item.scopes),
        }
        for import_name, item in sorted(
            workspace.workspace_ambiguous_imports.items(),
            key=lambda item: item[0],
        )
    }

    reports_payload = []
    for report in reports:
        ambiguous_payload = {
            import_name: sorted(candidates)
            for import_name, candidates in sorted(
                report.ambiguous_imports.items(),
                key=lambda item: item[0].lower(),
            )
        }
        reports_payload.append(
            {
                "name": report.name,
                "path": str(report.path),
                "python_files": report.python_files,
                "stdlib_imports": sorted(report.stdlib_imports),
                "local_imports": sorted(report.local_imports),
                "external_imports": sorted(report.external_imports),
                "used_dependencies": sorted(report.used_dependencies),
                "indirect_in_shared": sorted(report.indirect_in_shared),
                "missing_in_shared": sorted(report.missing_in_shared),
                "ambiguous_imports": ambiguous_payload,
                "unresolved_imports": sorted(report.unresolved_imports),
                "parse_errors": [
                    {"file": parse_error.file, "message": parse_error.message}
                    for parse_error in sorted(
                        report.parse_errors,
                        key=lambda item: (item.file, item.message),
                    )
                ],
            }
        )

    return {
        "project_root": str(project_root),
        "core_path": str(core_path),
        "modules_path": str(modules_path),
        "summary": {
            "scopes_scanned": summary.scopes_scanned,
            "total_parse_errors": summary.total_parse_errors,
            "total_missing_in_shared": summary.total_missing_in_shared,
            "total_unused_in_shared": summary.total_unused_in_shared,
        },
        "reports": reports_payload,
        "workspace": {
            "shared_pyproject": (
                str(workspace.shared_pyproject_path)
                if workspace.shared_pyproject_path
                else None
            ),
            "comparison_available": workspace.comparison_available,
            "declared_shared": sorted(workspace.declared_shared),
            "workspace_used": sorted(workspace.workspace_used),
            "unused_in_shared": sorted(workspace.unused_in_shared),
            "dependency_scopes": dependency_scopes_payload,
            "shared_dependencies": sorted(workspace.shared_dependencies),
            "exclusive_dependencies_by_scope": exclusive_payload,
            "workspace_indirect_dependencies": sorted(
                workspace.workspace_indirect_dependencies
            ),
            "workspace_ambiguous_imports": workspace_ambiguous_payload,
            "workspace_unresolved_imports": sorted(workspace.workspace_unresolved_imports),
            "ignored_dependencies": sorted(workspace.ignored_dependencies),
            "dependency_compare_error": workspace.dependency_compare_error,
        },
    }


class Command(BaseCommand):
    help = (
        "Scan imports in core/modules and decompose dependency usage against "
        "shared root pyproject.toml."
    )

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
        parser.add_argument(
            "--strict",
            dest="strict",
            action="store_true",
            help="Return non-zero exit code on dependency issues.",
        )
        parser.add_argument(
            "--fail-on-declared-not-used",
            dest="fail_on_declared_not_used",
            action="store_true",
            help="In strict mode, fail when shared declared dependencies are unused.",
        )

    def handle(self, *args: tuple, **options: dict) -> None:
        _ = options["action"]
        strict = bool(options.get("strict"))
        fail_on_declared_not_used = bool(options.get("fail_on_declared_not_used"))

        if fail_on_declared_not_used and not strict:
            raise CommandError("--fail-on-declared-not-used requires --strict")

        project_root = detect_project_root(options.get("root"))
        core_path = detect_core_path(project_root)
        modules_path = project_root / "modules"
        if not modules_path.is_dir():
            raise CommandError(f"Modules directory not found: {modules_path}")

        shared_pyproject_path = find_shared_pyproject(project_root)
        compare_available = False
        declared_shared: set[str] = set()
        transitive_from_declared: set[str] = set()
        overrides = DepsOverrides()
        dependency_compare_error: str | None = None

        if not shared_pyproject_path:
            dependency_compare_error = "Root pyproject.toml not found (comparison skipped)"
        else:
            try:
                pyproject_data = load_toml(shared_pyproject_path)
                declared_shared = extract_declared_dependencies(pyproject_data)
                overrides = extract_deps_overrides(pyproject_data)
                compare_available = True
            except Exception as exc:
                dependency_compare_error = f"Failed to parse root pyproject.toml: {exc}"

        if compare_available:
            lock_path = project_root / "poetry.lock"
            if not lock_path.is_file():
                dependency_compare_error = (
                    "poetry.lock not found (indirect classification skipped)"
                )
            else:
                try:
                    dependency_graph = load_poetry_dependency_graph(lock_path)
                    transitive_from_declared = compute_transitive_from_declared(
                        declared_shared,
                        dependency_graph,
                    )
                except Exception as exc:
                    dependency_compare_error = f"Failed to parse poetry.lock: {exc}"

        exact_map, ambiguous_map = build_resolver_maps(overrides)

        common_local_import_names = build_common_local_import_names(modules_path)
        stdlib_names = set(sys.builtin_module_names)
        stdlib_names.update(getattr(sys, "stdlib_module_names", set()))

        reports: list[ScopeReport] = []

        core_local_names = common_local_import_names | collect_scope_local_import_names(core_path)
        reports.append(
            scan_scope(
                name="core",
                scope_path=core_path,
                project_root=project_root,
                local_import_names=core_local_names,
                stdlib_names=stdlib_names,
                exact_map=exact_map,
                ambiguous_map=ambiguous_map,
                ignore_imports=overrides.ignore_imports,
            )
        )

        for module_dir in iter_module_dirs(modules_path):
            module_local_names = (
                common_local_import_names | collect_scope_local_import_names(module_dir)
            )
            reports.append(
                scan_scope(
                    name=f"module:{module_dir.name}",
                    scope_path=module_dir,
                    project_root=project_root,
                    local_import_names=module_local_names,
                    stdlib_names=stdlib_names,
                    exact_map=exact_map,
                    ambiguous_map=ambiguous_map,
                    ignore_imports=overrides.ignore_imports,
                )
            )

        workspace = build_workspace_report(
            reports=reports,
            shared_pyproject_path=shared_pyproject_path,
            comparison_available=compare_available,
            declared_shared=declared_shared,
            transitive_from_declared=transitive_from_declared,
            ignore_dependencies=overrides.ignore_dependencies,
            dependency_compare_error=dependency_compare_error,
        )
        summary = build_summary(reports, workspace)

        if options.get("as_json"):
            payload = build_json_payload(
                project_root=project_root,
                core_path=core_path,
                modules_path=modules_path,
                summary=summary,
                reports=reports,
                workspace=workspace,
            )
            self.stdout.write(json.dumps(payload, indent=2, sort_keys=True))
        else:
            self._print_human_report(
                project_root=project_root,
                core_path=core_path,
                modules_path=modules_path,
                summary=summary,
                reports=reports,
                workspace=workspace,
            )

        if strict:
            exit_code = evaluate_strict_exit_code(
                summary,
                fail_on_declared_not_used=fail_on_declared_not_used,
            )
            if exit_code != 0:
                raise SystemExit(exit_code)

    def _print_human_report(
        self,
        *,
        project_root: Path,
        core_path: Path,
        modules_path: Path,
        summary: ScanSummary,
        reports: list[ScopeReport],
        workspace: WorkspaceReport,
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
            self._write_set("indirect in shared", report.indirect_in_shared)

            if workspace.comparison_available:
                self._write_set("missing in shared", report.missing_in_shared)
            else:
                self.stdout.write("  missing in shared: comparison skipped")

            self._write_ambiguous_imports(report.ambiguous_imports)
            self._write_set("unresolved imports", report.unresolved_imports)

            if report.parse_errors:
                self.stdout.write(
                    self.style.WARNING(f"  parse errors: {len(report.parse_errors)}")
                )
                for parse_error in sorted(
                    report.parse_errors,
                    key=lambda item: (item.file, item.message),
                ):
                    self.stdout.write(f"    - {parse_error.file}: {parse_error.message}")
            else:
                self.stdout.write("  parse errors: 0")

        self.stdout.write("")
        self.stdout.write("[workspace]")
        if workspace.shared_pyproject_path:
            self.stdout.write(f"  shared pyproject: {workspace.shared_pyproject_path}")
        else:
            self.stdout.write("  shared pyproject: not found")

        self.stdout.write(f"  comparison available: {workspace.comparison_available}")

        if workspace.dependency_compare_error:
            self.stdout.write(
                self.style.WARNING(
                    f"  dependency compare error: {workspace.dependency_compare_error}"
                )
            )

        self._write_set("declared in shared", workspace.declared_shared)
        self._write_set("workspace used", workspace.workspace_used)
        self._write_set("unused in shared", workspace.unused_in_shared)
        self._write_set("shared dependencies", workspace.shared_dependencies)
        self._write_set(
            "workspace indirect dependencies",
            workspace.workspace_indirect_dependencies,
        )
        self._write_workspace_ambiguous_imports(workspace.workspace_ambiguous_imports)
        self._write_set(
            "workspace unresolved imports",
            workspace.workspace_unresolved_imports,
        )
        self._write_set("ignored dependencies", workspace.ignored_dependencies)

        has_exclusive = any(
            bool(dependencies)
            for dependencies in workspace.exclusive_dependencies_by_scope.values()
        )
        if not has_exclusive:
            self.stdout.write("  exclusive dependencies by scope: -")
        else:
            self.stdout.write("  exclusive dependencies by scope:")
            for scope_name, dependencies in sorted(
                workspace.exclusive_dependencies_by_scope.items(),
                key=lambda item: item[0].lower(),
            ):
                if not dependencies:
                    continue
                self.stdout.write(
                    f"    - {scope_name} ({len(dependencies)}): "
                    f"{', '.join(sorted(dependencies))}"
                )

        self.stdout.write("")
        self.stdout.write("[summary]")
        self.stdout.write(f"  scopes_scanned: {summary.scopes_scanned}")
        self.stdout.write(f"  total_parse_errors: {summary.total_parse_errors}")
        self.stdout.write(f"  total_missing_in_shared: {summary.total_missing_in_shared}")
        self.stdout.write(f"  total_unused_in_shared: {summary.total_unused_in_shared}")

    def _write_set(self, title: str, values: set[str]) -> None:
        if not values:
            self.stdout.write(f"  {title}: -")
            return
        self.stdout.write(f"  {title} ({len(values)}): {', '.join(sorted(values))}")

    def _write_ambiguous_imports(self, values: dict[str, set[str]]) -> None:
        if not values:
            self.stdout.write("  ambiguous imports: -")
            return

        self.stdout.write(f"  ambiguous imports ({len(values)}):")
        for import_name, candidates in sorted(values.items(), key=lambda item: item[0].lower()):
            self.stdout.write(
                f"    - {import_name}: {', '.join(sorted(candidates))}"
            )

    def _write_workspace_ambiguous_imports(
        self,
        values: dict[str, WorkspaceAmbiguousImport],
    ) -> None:
        if not values:
            self.stdout.write("  workspace ambiguous imports: -")
            return

        self.stdout.write(f"  workspace ambiguous imports ({len(values)}):")
        for import_name, item in sorted(values.items(), key=lambda pair: pair[0]):
            self.stdout.write(
                f"    - {import_name}: candidates={', '.join(sorted(item.candidates))}; "
                f"scopes={', '.join(sorted(item.scopes))}"
            )
