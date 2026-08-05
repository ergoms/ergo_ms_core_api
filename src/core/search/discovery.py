"""Discovery search_indexes.py из модулей."""

from __future__ import annotations

import importlib
import logging
from typing import Any

from .registry import SearchIndexDefinition, register_index

logger = logging.getLogger('search')


def _coerce_definition(raw: dict[str, Any]) -> SearchIndexDefinition | None:
  uid = (raw.get('uid') or '').strip()
  if not uid:
    return None
  build_document = raw.get('build_document')
  get_queryset = raw.get('get_queryset')
  if not callable(build_document) or not callable(get_queryset):
    return None
  return SearchIndexDefinition(
    uid=uid,
    primary_key=str(raw.get('primary_key') or 'id'),
    searchable_attributes=tuple(raw.get('searchable_attributes') or ()),
    filterable_attributes=tuple(raw.get('filterable_attributes') or ()),
    sortable_attributes=tuple(raw.get('sortable_attributes') or ()),
    build_document=build_document,
    get_queryset=get_queryset,
    ranking_rules=tuple(raw.get('ranking_rules') or SearchIndexDefinition.ranking_rules),
  )


def load_module_search_indexes() -> None:
  from src.core.utils.auto_api.discovered_apps_cache import get_discovered_apps

  for app_path in get_discovered_apps():
    module_path = f'{app_path}.search_indexes'
    try:
      mod = importlib.import_module(module_path)
    except ImportError:
      continue
    except Exception:
      logger.warning('Ошибка загрузки search_indexes из %s', module_path, exc_info=True)
      continue

    entries = getattr(mod, 'SEARCH_INDEXES', None)
    if not entries:
      continue
    if not isinstance(entries, (list, tuple)):
      continue
    for raw in entries:
      if not isinstance(raw, dict):
        continue
      defn = _coerce_definition(raw)
      if defn:
        register_index(defn)
