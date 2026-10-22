"""Reference results and independent contracts for the table statistics API."""
from datetime import date
import json
import os
from pathlib import Path
import subprocess
import sys
import unittest

import polars as pl
from polars.testing import assert_frame_equal

from src.core.analytics import eda
from .frames import canonical_result, reference_frames


def compute_result(frame):
    return {
        'summary': eda.compute_summary(frame),
        'distributions': eda.compute_distributions(frame),
        'correlations': eda.compute_correlations(frame),
        'outliers': eda.compute_outliers(frame),
    }


class EdaReferenceTests(unittest.TestCase):
    def test_results_match_reference_tables(self):
        fixtures = Path(__file__).with_name('fixtures')
        for name, frame in reference_frames().items():
            with self.subTest(table=name):
                expected = json.loads((fixtures / f'{name}.json').read_text(encoding='utf-8'))
                actual = canonical_result(compute_result(frame))
                self.assertEqual(actual, expected)
                json.dumps(actual, allow_nan=False)

    def test_computations_do_not_mutate_the_input(self):
        for frame in reference_frames().values():
            original = frame.clone()
            compute_result(frame)
            assert_frame_equal(frame, original)


class EdaContractTests(unittest.TestCase):
    def test_summary_uses_sample_deviation_and_preserves_null_unique_semantics(self):
        entry = eda.compute_summary(pl.DataFrame({'x': [1, 2, 3, None]}))[0]
        self.assertEqual(entry, {
            'name': 'x', 'dtype': 'Int64', 'count': 4, 'nulls': 1, 'null_pct': 25.0,
            'unique': 4, 'min': 1, 'max': 3, 'mean': 2.0, 'median': 2.0,
            'std': 1.0, 'q25': 2.0, 'q75': 3.0,
        })

    def test_all_supported_numeric_types_are_analyzed_as_numbers(self):
        for dtype in eda.NUMERIC_TYPES:
            with self.subTest(dtype=dtype):
                frame = pl.DataFrame({'x': pl.Series([0, 1, 2, 3, None], dtype=dtype)})
                self.assertEqual(eda.compute_summary(frame)[0]['mean'], 1.5)
                self.assertIn('x', eda.compute_distributions(frame)['numeric'])
                self.assertEqual(len(eda.compute_outliers(frame)), 1)

    def test_boolean_and_dates_keep_their_categorical_contract(self):
        frame = pl.DataFrame({'flag': [True, True, False], 'day': [date(2024, 1, 1)] * 3})
        result = eda.compute_distributions(frame)
        self.assertEqual(result['numeric'], {})
        self.assertEqual(set(result['categorical']), {'flag', 'day'})
        self.assertEqual(result['categorical']['day'], {'values': ['2024-01-01'], 'counts': [3]})

    def test_histogram_counts_every_non_null_finite_value(self):
        result = eda.compute_distributions(pl.DataFrame({'x': list(range(120)) + [None]}))['numeric']['x']
        self.assertEqual(sum(result['counts']), 120)
        self.assertEqual(len(result['bins']), len(result['counts']))

    def test_categorical_distribution_is_limited_to_fifteen_most_frequent_values(self):
        values = [str(i) for i in range(20) for _ in range(i + 1)]
        result = eda.compute_distributions(pl.DataFrame({'x': values}))['categorical']['x']
        self.assertEqual(result['values'], [str(i) for i in range(19, 4, -1)])
        self.assertEqual(result['counts'], list(range(20, 5, -1)))

    def test_correlations_limit_the_matrix_and_keep_field_order(self):
        frame = pl.DataFrame({f'field_{i}': [i, i + 1, i + 2] for i in range(32)})
        result = eda.compute_correlations(frame)
        self.assertEqual(result['fields'], frame.columns[:30])
        self.assertEqual(result['matrix'], [[1.0] * 30 for _ in range(30)])

    def test_outlier_percentage_uses_total_rows_including_nulls(self):
        frame = pl.DataFrame({'x': [0.0, 1.0, 2.0, 3.0, 100.0, None]})
        result = eda.compute_outliers(frame)[0]
        self.assertEqual(result['count'], 1)
        self.assertEqual(result['pct'], 16.67)
        self.assertEqual(result['lower_bound'], -2.0)
        self.assertEqual(result['upper_bound'], 6.0)

    def test_empty_untyped_table_is_supported(self):
        self.assertEqual(compute_result(pl.DataFrame()), {
            'summary': [], 'distributions': {'numeric': {}, 'categorical': {}},
            'correlations': {'fields': [], 'matrix': []}, 'outliers': [],
        })


class AnalyticsIsolationTests(unittest.TestCase):
    def _run_script(self, script):
        environment = {**os.environ, 'PYTHONPATH': str(Path(__file__).resolve().parents[4])}
        return subprocess.run([sys.executable, '-c', script], env=environment,
                              capture_output=True, text=True, timeout=30)

    def test_operations_import_and_execute_without_framework_or_domain_packages(self):
        script = '''import importlib.abc,sys
class BlockFramework(importlib.abc.MetaPathFinder):
    def find_spec(self, fullname, path=None, target=None):
        if fullname.split('.')[0] in {'django','celery','rest_framework','modules'}:
            raise ImportError('Framework/domain import attempted: '+fullname)
sys.meta_path.insert(0,BlockFramework())
import polars as pl
from src.core.analytics.eda import compute_summary
assert compute_summary(pl.DataFrame({'x':[1,2,3]}))[0]['mean']==2
'''
        result = self._run_script(script)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_importing_the_package_does_not_load_optional_computation_libraries(self):
        # A fresh process makes this independent of the test runner's imports.
        script = 'import sys; import src.core.analytics; assert not ({"polars","numpy","statsmodels","django"} & sys.modules.keys())'
        result = self._run_script(script)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
