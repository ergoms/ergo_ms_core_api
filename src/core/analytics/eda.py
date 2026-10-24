"""Column statistics, distributions, correlations and IQR outliers on Polars.

Callers supply an already prepared DataFrame. These operations perform no I/O,
sampling, persistence or framework initialization and do not modify the frame.
"""
import logging
import math
from typing import Any, Dict, List

import polars as pl

logger = logging.getLogger(__name__)

NUMERIC_TYPES = (
    pl.Int8, pl.Int16, pl.Int32, pl.Int64,
    pl.UInt8, pl.UInt16, pl.UInt32, pl.UInt64,
    pl.Float32, pl.Float64, pl.Decimal,
)

HISTOGRAM_BINS = 20
TOP_N_CATEGORIES = 15


def _safe_scalar(val: Any) -> Any:
    if val is None:
        return None
    if isinstance(val, float) and (math.isnan(val) or math.isinf(val)):
        return None
    if hasattr(val, 'item'):
        return val.item()
    return val


def _is_numeric(dtype: pl.DataType) -> bool:
    return isinstance(dtype, NUMERIC_TYPES)


def _statistics_series(series: pl.Series) -> pl.Series:
    # Statistical operations use Float64; Decimal histograms are unsupported.
    # Keep the caller's exact Decimal column and its metadata unchanged.
    return series.cast(pl.Float64) if isinstance(series.dtype, pl.Decimal) else series


def _numeric_columns(df: pl.DataFrame) -> List[str]:
    return [c for c in df.columns if _is_numeric(df[c].dtype)]


def _categorical_columns(df: pl.DataFrame) -> List[str]:
    return [c for c in df.columns if not _is_numeric(df[c].dtype)]


def compute_summary(df: pl.DataFrame) -> List[Dict[str, Any]]:
    total = len(df)
    result = []

    for col_name in df.columns:
        series = df[col_name]
        null_count = series.null_count()
        entry: Dict[str, Any] = {
            'name': col_name,
            'dtype': str(series.dtype),
            'count': total,
            'nulls': null_count,
            'null_pct': round(null_count / total * 100, 2) if total else 0,
            'unique': series.n_unique(),
        }

        if _is_numeric(series.dtype):
            desc = _statistics_series(series.drop_nulls())
            if len(desc) > 0:
                entry.update({
                    'min': _safe_scalar(desc.min()),
                    'max': _safe_scalar(desc.max()),
                    'mean': _safe_scalar(desc.mean()),
                    'median': _safe_scalar(desc.median()),
                    'std': _safe_scalar(desc.std()),
                    'q25': _safe_scalar(desc.quantile(0.25)),
                    'q75': _safe_scalar(desc.quantile(0.75)),
                })
            else:
                for k in ('min', 'max', 'mean', 'median', 'std', 'q25', 'q75'):
                    entry[k] = None
        else:
            for k in ('min', 'max', 'mean', 'median', 'std', 'q25', 'q75'):
                entry[k] = None

        result.append(entry)

    return result


def compute_distributions(df: pl.DataFrame) -> Dict[str, Any]:
    numeric = {}
    categorical = {}

    for col_name in _numeric_columns(df):
        series = _statistics_series(df[col_name].drop_nulls())
        if len(series) == 0:
            continue
        try:
            hist = series.hist(bin_count=HISTOGRAM_BINS)
            bins = []
            counts = []
            for row in hist.iter_rows(named=True):
                bp = row.get('breakpoint') or row.get('break_point') or row.get('category')
                cnt = row.get('count', 0)
                bins.append(_safe_scalar(bp))
                counts.append(int(cnt))
            numeric[col_name] = {'bins': bins, 'counts': counts}
        except Exception as exc:
            logger.debug("Гистограмма для %s пропущена: %s", col_name, exc)

    for col_name in _categorical_columns(df):
        series = df[col_name].drop_nulls().cast(pl.Utf8)
        if len(series) == 0:
            continue
        vc = series.value_counts().sort('count', descending=True).head(TOP_N_CATEGORIES)
        values = vc[col_name].to_list()
        counts = vc['count'].to_list()
        categorical[col_name] = {'values': values, 'counts': [int(c) for c in counts]}

    return {'numeric': numeric, 'categorical': categorical}


def compute_correlations(df: pl.DataFrame) -> Dict[str, Any]:
    num_cols = _numeric_columns(df)
    if len(num_cols) < 2:
        return {'fields': num_cols, 'matrix': []}

    # Keep the established 30-field result limit and caller-provided field order.
    num_cols = num_cols[:30]
    sub = pl.DataFrame({name: _statistics_series(df[name]) for name in num_cols})

    matrix = []
    for col_a in num_cols:
        row = []
        for col_b in num_cols:
            try:
                corr_val = sub.select(pl.corr(col_a, col_b)).item()
                row.append(_safe_scalar(round(corr_val, 4)) if corr_val is not None else None)
            except Exception as exc:
                # Preserve a missing cell when a pair cannot be correlated.
                logger.debug("Корреляция %s / %s пропущена: %s", col_a, col_b, exc)
                row.append(None)
        matrix.append(row)

    return {'fields': num_cols, 'matrix': matrix}


def compute_outliers(df: pl.DataFrame) -> List[Dict[str, Any]]:
    result = []
    total = len(df)

    for col_name in _numeric_columns(df):
        series = _statistics_series(df[col_name].drop_nulls())
        if len(series) < 4:
            continue

        q1 = series.quantile(0.25)
        q3 = series.quantile(0.75)
        if q1 is None or q3 is None:
            continue

        iqr = q3 - q1
        lower = q1 - 1.5 * iqr
        upper = q3 + 1.5 * iqr

        outlier_count = int(series.filter((series < lower) | (series > upper)).len())

        result.append({
            'name': col_name,
            'count': outlier_count,
            'pct': round(outlier_count / total * 100, 2) if total else 0,
            'lower_bound': _safe_scalar(round(lower, 4)),
            'upper_bound': _safe_scalar(round(upper, 4)),
            'q1': _safe_scalar(round(q1, 4)),
            'q3': _safe_scalar(round(q3, 4)),
            'iqr': _safe_scalar(round(iqr, 4)),
        })

    return result
