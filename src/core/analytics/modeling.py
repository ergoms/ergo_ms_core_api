"""
Движок статистического моделирования: линейная регрессия, ARIMA, SARIMA, box plot.

Принимает Polars DataFrame и config dict, возвращает dict с результатами.
"""
import logging
from typing import Any, Callable, Dict, Optional

import numpy as np
import polars as pl

from .eda import NUMERIC_TYPES

logger = logging.getLogger(__name__)

ProgressCb = Optional[Callable[[float, str], None]]


def _is_numeric_dtype(dtype: pl.DataType) -> bool:
    return isinstance(dtype, NUMERIC_TYPES)


def _progress(cb: ProgressCb, val: float, msg: str):
    if cb:
        cb(val, msg)


def _safe_float(val) -> Optional[float]:
    if val is None:
        return None
    v = float(val)
    if np.isnan(v) or np.isinf(v):
        return None
    return round(v, 6)


def run_linear_regression(
    df: pl.DataFrame,
    config: Dict[str, Any],
    progress_cb: ProgressCb = None,
) -> Dict[str, Any]:
    """
    OLS через statsmodels.
    config: { target_field: str, feature_fields: list[str] }
    """
    import statsmodels.api as sm

    target = config['target_field']
    features = config['feature_fields']

    _progress(progress_cb, 0.05, 'Подготовка данных')

    cols = [target] + features
    sub = df.select(cols).drop_nulls()
    n_rows = len(sub)

    y = sub[target].to_numpy().astype(float)
    X = sub.select(features).to_numpy().astype(float)
    X = sm.add_constant(X)

    _progress(progress_cb, 0.20, f'Обучение модели ({n_rows} строк)')

    model = sm.OLS(y, X).fit()

    _progress(progress_cb, 0.70, 'Сбор результатов')

    coef_names = ['const'] + features
    coefficients = []
    for i, name in enumerate(coef_names):
        coefficients.append({
            'name': name,
            'coef': _safe_float(model.params[i]),
            'std_err': _safe_float(model.bse[i]),
            't_value': _safe_float(model.tvalues[i]),
            'p_value': _safe_float(model.pvalues[i]),
        })

    residuals = model.resid.tolist()[:200]

    _progress(progress_cb, 0.95, 'Формирование результата')

    return {
        'model_type': 'linear',
        'coefficients': coefficients,
        'metrics': {
            'r_squared': _safe_float(model.rsquared),
            'r_squared_adj': _safe_float(model.rsquared_adj),
            'f_statistic': _safe_float(model.fvalue),
            'f_pvalue': _safe_float(model.f_pvalue),
            'aic': _safe_float(model.aic),
            'bic': _safe_float(model.bic),
        },
        'meta': {
            'n_observations': n_rows,
            'n_features': len(features),
            'target_field': target,
            'feature_fields': features,
        },
        'residuals_sample': [_safe_float(r) for r in residuals],
    }


def run_arima(
    df: pl.DataFrame,
    config: Dict[str, Any],
    progress_cb: ProgressCb = None,
) -> Dict[str, Any]:
    """
    ARIMA через statsmodels.
    config: { value_field: str, date_field: str, p: int, d: int, q: int, forecast_steps: int? }
    """
    from statsmodels.tsa.arima.model import ARIMA

    value_field = config['value_field']
    date_field = config['date_field']
    p = int(config.get('p', 1))
    d = int(config.get('d', 1))
    q = int(config.get('q', 1))
    forecast_steps = int(config.get('forecast_steps', 10))

    _progress(progress_cb, 0.05, 'Подготовка временного ряда')

    sub = df.select([date_field, value_field]).drop_nulls().sort(date_field)
    n_rows = len(sub)
    y = sub[value_field].to_numpy().astype(float)

    _progress(progress_cb, 0.15, f'Обучение ARIMA({p},{d},{q}) на {n_rows} точках')

    model = ARIMA(y, order=(p, d, q)).fit()

    _progress(progress_cb, 0.65, 'Прогноз')

    forecast = model.forecast(steps=forecast_steps)

    _progress(progress_cb, 0.85, 'Сбор результатов')

    params = {}
    for k, v in model.params.items() if hasattr(model.params, 'items') else enumerate(model.params):
        params[str(k)] = _safe_float(v)

    return {
        'model_type': 'arima',
        'order': {'p': p, 'd': d, 'q': q},
        'params': params,
        'metrics': {
            'aic': _safe_float(model.aic),
            'bic': _safe_float(model.bic),
            'hqic': _safe_float(model.hqic),
        },
        'forecast': [_safe_float(v) for v in forecast],
        'residuals_sample': [_safe_float(r) for r in model.resid.tolist()[:200]],
        'meta': {
            'n_observations': n_rows,
            'value_field': value_field,
            'date_field': date_field,
            'forecast_steps': forecast_steps,
        },
    }


def run_sarima(
    df: pl.DataFrame,
    config: Dict[str, Any],
    progress_cb: ProgressCb = None,
) -> Dict[str, Any]:
    """
    SARIMA (SARIMAX) через statsmodels.
    config: { value_field, date_field, p, d, q, P, D, Q, m, forecast_steps? }
    """
    from statsmodels.tsa.statespace.sarimax import SARIMAX

    value_field = config['value_field']
    date_field = config['date_field']
    p = int(config.get('p', 1))
    d = int(config.get('d', 1))
    q = int(config.get('q', 1))
    P = int(config.get('P', 1))
    D = int(config.get('D', 1))
    Q = int(config.get('Q', 1))
    m = int(config.get('m', 12))
    forecast_steps = int(config.get('forecast_steps', 10))

    _progress(progress_cb, 0.05, 'Подготовка временного ряда')

    sub = df.select([date_field, value_field]).drop_nulls().sort(date_field)
    n_rows = len(sub)
    y = sub[value_field].to_numpy().astype(float)

    _progress(progress_cb, 0.15, f'Обучение SARIMA({p},{d},{q})({P},{D},{Q},{m}) на {n_rows} точках')

    model = SARIMAX(y, order=(p, d, q), seasonal_order=(P, D, Q, m)).fit(disp=False)

    _progress(progress_cb, 0.65, 'Прогноз')

    forecast = model.forecast(steps=forecast_steps)

    _progress(progress_cb, 0.85, 'Сбор результатов')

    params = {}
    for k, v in model.params.items() if hasattr(model.params, 'items') else enumerate(model.params):
        params[str(k)] = _safe_float(v)

    return {
        'model_type': 'sarima',
        'order': {'p': p, 'd': d, 'q': q},
        'seasonal_order': {'P': P, 'D': D, 'Q': Q, 'm': m},
        'params': params,
        'metrics': {
            'aic': _safe_float(model.aic),
            'bic': _safe_float(model.bic),
            'hqic': _safe_float(model.hqic),
        },
        'forecast': [_safe_float(v) for v in forecast],
        'residuals_sample': [_safe_float(r) for r in model.resid.tolist()[:200]],
        'meta': {
            'n_observations': n_rows,
            'value_field': value_field,
            'date_field': date_field,
            'forecast_steps': forecast_steps,
        },
    }


def run_boxplot(
    df: pl.DataFrame,
    config: Dict[str, Any],
    progress_cb: ProgressCb = None,
) -> Dict[str, Any]:
    """
    Описательная статистика и границы ящика с усами (Tukey IQR).
    config: { fields: list[str] }
    """
    fields = config.get('fields') or []
    if not fields:
        raise ValueError('Укажите хотя бы одно поле в config.fields')

    n_rows_df = len(df)
    _progress(progress_cb, 0.05, 'Расчёт квантилей и усов')

    boxplots: list[Dict[str, Any]] = []
    total_outliers = 0
    n_fields = len(fields)

    for idx, col in enumerate(fields):
        if col not in df.columns:
            logger.warning('Поле %s отсутствует в датасете, пропуск', col)
            continue
        if not _is_numeric_dtype(df[col].dtype):
            logger.warning('Поле %s не числовое, пропуск', col)
            continue

        series = df[col].drop_nulls()
        n = len(series)
        if n < 1:
            continue

        q1 = series.quantile(0.25)
        q3 = series.quantile(0.75)
        if q1 is None or q3 is None:
            continue

        f_q1 = float(q1)
        f_q3 = float(q3)
        iqr = f_q3 - f_q1
        lower_fence = f_q1 - 1.5 * iqr
        upper_fence = f_q3 + 1.5 * iqr

        mn = float(series.min())
        mx = float(series.max())
        whisker_low = max(mn, lower_fence)
        whisker_high = min(mx, upper_fence)

        outlier_series = series.filter((series < lower_fence) | (series > upper_fence))
        outlier_count = int(outlier_series.len())
        total_outliers += outlier_count

        outliers_sample_raw = outlier_series.head(50).to_list()
        outliers_sample = [_safe_float(v) for v in outliers_sample_raw]

        median = series.median()
        mean = series.mean()

        boxplots.append({
            'field': col,
            'min': _safe_float(mn),
            'max': _safe_float(mx),
            'q1': _safe_float(f_q1),
            'median': _safe_float(median),
            'q3': _safe_float(f_q3),
            'mean': _safe_float(mean),
            'whisker_low': _safe_float(whisker_low),
            'whisker_high': _safe_float(whisker_high),
            'iqr': _safe_float(iqr),
            'lower_fence': _safe_float(lower_fence),
            'upper_fence': _safe_float(upper_fence),
            'outlier_count': outlier_count,
            'outliers_sample': outliers_sample,
        })

        if n_fields:
            frac = (idx + 1) / n_fields
            _progress(progress_cb, 0.05 + 0.85 * frac, f'Поле {col}')

    if not boxplots:
        raise ValueError('Нет подходящих числовых полей для анализа')

    _progress(progress_cb, 0.95, 'Формирование результата')

    return {
        'model_type': 'boxplot',
        'boxplots': boxplots,
        'metrics': {
            'total_fields': len(boxplots),
            'total_outliers': total_outliers,
        },
        'meta': {
            'n_observations': n_rows_df,
            'fields_analyzed': [b['field'] for b in boxplots],
        },
    }
