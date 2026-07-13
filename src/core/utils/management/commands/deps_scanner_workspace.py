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


