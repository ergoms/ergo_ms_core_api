"""Локальный снимок Hugging Face для sentence-transformers и аналогов."""

from __future__ import annotations

import sys
from pathlib import Path


def resolve_huggingface_source(repo_id: str, *, root: Path | None = None) -> str:
    """Путь к готовому снимку или исходный org/name, если весов ещё нет."""
    from src.core.utils.database.module_schema import project_root

    project = (root or project_root()).resolve()
    deploy = str(project / 'core' / 'deployment')
    if deploy not in sys.path:
        sys.path.insert(0, deploy)
    from project_layout import resolve_huggingface_source as resolve_on_disk

    return resolve_on_disk(project, repo_id)
