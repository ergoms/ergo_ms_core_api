"""Deterministic inputs shared by numerical compatibility checks."""
from datetime import date, timedelta
import math
import random

import polars as pl


def regression_frame(rows=48, seed=20261023):
    rng = random.Random(seed)
    x = [i / 10 for i in range(rows)]
    z = [math.sin(i / 3) for i in range(rows)]
    y = [2 + 3 * a - 1.5 * b + rng.uniform(-0.1, 0.1) for a, b in zip(x, z)]
    return pl.DataFrame({'y': y + [None, 4.0], 'x': x + [1.0, None], 'z': z + [0.0, 1.0]})


def time_series_frame(rows=64, seed=20261023):
    rng = random.Random(seed)
    values = []
    previous = 0.0
    for i in range(rows):
        previous = 0.55 * previous + rng.uniform(-0.5, 0.5)
        values.append(8 + math.sin(i * math.pi / 2) + previous)
    days = [date(2024, 1, 1) + timedelta(days=i) for i in range(rows)]
    # Reverse order and incomplete rows exercise preparation before fitting.
    return pl.DataFrame({'day': days[::-1] + [None, date(2025, 1, 1)],
                         'value': values[::-1] + [2.0, None]})


def reference_cases():
    return {
        'boxplot': ('run_boxplot', pl.DataFrame({
            'x': [0.0, 1.0, 2.0, 3.0, 100.0, None],
            'constant': [4] * 6, 'label': ['a'] * 6,
            'empty': pl.Series([None] * 6, dtype=pl.Float64),
        }), {'fields': ['missing', 'x', 'label', 'empty', 'constant']}),
        'linear': ('run_linear_regression', regression_frame(),
                   {'target_field': 'y', 'feature_fields': ['x', 'z']}),
        'arima': ('run_arima', time_series_frame(),
                  {'date_field': 'day', 'value_field': 'value', 'p': 1, 'd': 0, 'q': 0, 'forecast_steps': 5}),
        'sarima': ('run_sarima', time_series_frame(),
                   {'date_field': 'day', 'value_field': 'value', 'p': 1, 'd': 0, 'q': 0,
                    'P': 1, 'D': 0, 'Q': 0, 'm': 4, 'forecast_steps': 5}),
    }
