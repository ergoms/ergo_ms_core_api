"""Conversions between prepared row data and Polars, without source access."""
from __future__ import annotations

from typing import TYPE_CHECKING, Any, Sequence

if TYPE_CHECKING:
    import polars as pl


def rows_to_frame(
    columns: Sequence[str] | None,
    rows: Sequence[Sequence[Any]] | None,
) -> pl.DataFrame:
    # Polars грузится по вызову: модули импортируют этот файл при старте API.
    import polars as pl

    columns = list(columns or [])
    rows = list(rows or [])
    if not columns:
        return pl.DataFrame()
    if not rows:
        return pl.DataFrame({column: [] for column in columns})
    data = {
        column: [row[index] if index < len(row) else None for row in rows]
        for index, column in enumerate(columns)
    }
    return pl.DataFrame(data)


def frame_to_rows(frame: pl.DataFrame) -> tuple[list[str], list[list[Any]]]:
    columns = list(frame.columns)
    if not columns:
        return [], []
    return columns, [list(row) for row in frame.iter_rows()]
