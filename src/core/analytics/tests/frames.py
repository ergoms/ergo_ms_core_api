"""Deterministic tables shared by reference and contract checks."""
from datetime import date

import polars as pl


def reference_frames() -> dict[str, pl.DataFrame]:
    first, second, third = date(2024, 1, 1), date(2024, 1, 2), date(2024, 1, 3)
    return {
        'mixed': pl.DataFrame({
            'amount': [0.0, 1.5, None, -3.0, 10.0, 2.5, 4.0, 100.0],
            'units': [0, 1, 2, None, 4, 5, 6, 7],
            'category': ['А', 'А', 'Б', 'А', 'Б', None, 'А', 'В'],
            'day': [first, first, second, first, second, None, first, third],
        }),
        'empty': pl.DataFrame(schema={'amount': pl.Float64, 'units': pl.Int64,
                                      'category': pl.String, 'day': pl.Date}),
        'all_null': pl.DataFrame({
            'amount': pl.Series([None] * 6, dtype=pl.Float64),
            'category': pl.Series([None] * 6, dtype=pl.String),
            'day': pl.Series([None] * 6, dtype=pl.Date),
        }),
        'single_row': pl.DataFrame({'amount': [7.5], 'category': ['one'], 'day': [first]}),
        'constant': pl.DataFrame({'amount': [5.0] * 8, 'zero': [0.0] * 8,
                                  'flag': [True] * 8}),
        'non_finite': pl.DataFrame({
            'amount': [float('nan'), float('inf'), -float('inf'), 0.0, 1.0, None],
            'units': [1, 2, 3, 4, 5, 6],
        }),
    }


def canonical_result(result: dict) -> dict:
    # Equal-frequency value_counts rows have no stable order in Polars. Compare
    # the category/count pairs, while keeping every other result order intact.
    distributions = dict(result['distributions'])
    categorical = {}
    for name, entry in distributions['categorical'].items():
        pairs = sorted(zip(entry['values'], entry['counts']), key=lambda item: (-item[1], item[0]))
        categorical[name] = {'values': [p[0] for p in pairs], 'counts': [p[1] for p in pairs]}
    distributions['categorical'] = categorical
    return {**result, 'distributions': distributions}
