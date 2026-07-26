from __future__ import annotations

import re
import tomllib

from dataclasses import dataclass, field
from pathlib import Path

from django.conf import settings
from django.core.management.base import CommandError


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
