"""Column profile normalization without queries, persistence or field models."""
from __future__ import annotations

import math
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

FieldSpec = Tuple[str, bool]


def _json_number(val: Any) -> Optional[float]:
    if val is None or isinstance(val, bool):
        return None
    try:
        number = float(val)
    except (TypeError, ValueError):
        return None
    if not math.isfinite(number):
        return None
    return number


def _as_int(val: Any) -> int:
    try:
        return int(val) if val is not None else 0
    except (TypeError, ValueError):
        return 0


def summary_from_aggregate_row(
    specs: Sequence[FieldSpec],
    row: Sequence[Any],
) -> Tuple[int, List[Dict[str, Any]]]:
    """Разбирает строку агрегатов в профиль колонок."""
    total = _as_int(row[0] if row else 0)
    cursor = 1
    summary: List[Dict[str, Any]] = []
    for name, numeric in specs:
        non_null = _as_int(row[cursor])
        unique = _as_int(row[cursor + 1])
        cursor += 2
        min_v = max_v = mean_v = std_v = None
        if numeric:
            min_v = _json_number(row[cursor])
            max_v = _json_number(row[cursor + 1])
            mean_v = _json_number(row[cursor + 2])
            std_v = _json_number(row[cursor + 3])
            cursor += 4
        nulls = max(total - non_null, 0)
        summary.append({
            'name': name,
            'count': total,
            'nulls': nulls,
            'null_pct': round(nulls / total * 100, 2) if total else 0.0,
            'unique': unique,
            'min': min_v,
            'max': max_v,
            'mean': mean_v,
            'std': std_v,
        })
    return total, summary


def summary_from_entries(
    columns: Iterable[Tuple[str, str]],
    entries: Sequence[Dict[str, Any]],
    total_rows: int,
) -> List[Dict[str, Any]]:
    """Нормализует статистику колонок по переданным именам и источникам."""
    by_col = {
        entry.get('name'): entry
        for entry in entries
        if isinstance(entry, dict) and entry.get('name')
    }
    summary: List[Dict[str, Any]] = []
    for name, source_column in columns:
        entry = by_col.get(source_column) or by_col.get(name)
        if entry is None:
            continue
        nulls = _as_int(entry.get('nulls'))
        summary.append({
            'name': name,
            'count': total_rows,
            'nulls': nulls,
            'null_pct': _json_number(entry.get('null_pct')) or 0.0,
            'unique': _as_int(entry.get('unique')),
            'min': _json_number(entry.get('min')),
            'max': _json_number(entry.get('max')),
            'mean': _json_number(entry.get('mean')),
            'std': _json_number(entry.get('std')),
        })
    return summary
