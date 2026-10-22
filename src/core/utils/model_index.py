"""Runtime model references; reads never download unless explicitly allowed."""

from pathlib import Path
import sys


def resolve_model(provider: str, name: str, *, root: Path | None = None, allow_download=False) -> dict:
    if root is None:
        from src.core.utils.database.module_schema import project_root
        root = project_root()
    project = root.resolve()
    deployment = str(project / 'core/deployment')
    if deployment not in sys.path:
        sys.path.insert(0, deployment)
    from model_index import resolve_local_model
    return resolve_local_model(project, provider, name, allow_download=allow_download)
