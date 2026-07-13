"""Management command: scan Python dependencies."""

from django.core.management.base import BaseCommand

from .deps_scanner import *  # noqa: F403
from .deps_scanner_workspace import *  # noqa: F403

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
