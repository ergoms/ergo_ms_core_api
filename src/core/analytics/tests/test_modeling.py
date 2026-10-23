"""Numerical references captured before extracting statistical modeling."""
from copy import deepcopy
from contextlib import ExitStack
import json
import math
import os
from pathlib import Path
import subprocess
import sys
import unittest
from unittest.mock import patch

import polars as pl
from polars.testing import assert_frame_equal

from src.core.analytics import modeling
from .modeling_cases import reference_cases, regression_frame


class ModelingReferenceTests(unittest.TestCase):
    def assert_reference_equal(self, actual, expected, path='result'):
        if isinstance(expected, dict):
            self.assertEqual(set(actual), set(expected), path)
            for key, value in expected.items():
                self.assert_reference_equal(actual[key], value, f'{path}.{key}')
        elif isinstance(expected, list):
            self.assertEqual(len(actual), len(expected), path)
            for index, value in enumerate(expected):
                self.assert_reference_equal(actual[index], value, f'{path}[{index}]')
        elif isinstance(expected, float):
            # Solver/BLAS roundoff can differ across supported platforms.
            self.assertTrue(math.isclose(actual, expected, rel_tol=1e-6, abs_tol=1e-5),
                            f'{path}: {actual} != {expected}')
        else:
            self.assertEqual(actual, expected, path)

    def test_results_and_progress_match_original_execution(self):
        for name, (operation, frame, config) in reference_cases().items():
            with self.subTest(operation=name):
                expected = json.loads((Path(__file__).with_name('fixtures') /
                                       f'modeling_{name}.json').read_text(encoding='utf-8'))
                original_frame, original_config = frame.clone(), deepcopy(config)
                progress = []
                with ExitStack() as stack:
                    if name == 'sarima':
                        from statsmodels.tsa.statespace.sarimax import SARIMAX
                        # Native numerical fits differ on Windows/Linux. Keep
                        # the historical serialization check at the original fit.
                        stack.enter_context(patch.object(
                            SARIMAX, 'fit', autospec=True,
                            side_effect=lambda model, **kwargs: model.filter(expected['fit_parameters']),
                        ))
                    result = getattr(modeling, operation)(frame, config,
                                                           lambda value, message: progress.append([value, message]))
                self.assert_reference_equal(result, expected['result'])
                self.assertEqual(progress, expected['progress'])
                assert_frame_equal(frame, original_frame)
                self.assertEqual(config, original_config)
                json.dumps(result, allow_nan=False)


class BoxplotContractTests(unittest.TestCase):
    def test_tukey_fences_and_nulls_keep_the_existing_contract(self):
        result = modeling.run_boxplot(pl.DataFrame({'x': [0, 1, 2, 3, 100, None]}), {'fields': ['x']})
        box = result['boxplots'][0]
        self.assertEqual(result['meta']['n_observations'], 6)
        self.assertEqual((box['q1'], box['median'], box['q3']), (1.0, 2.0, 3.0))
        self.assertEqual((box['lower_fence'], box['upper_fence']), (-2.0, 6.0))
        self.assertEqual((box['whisker_low'], box['whisker_high']), (0.0, 6.0))
        self.assertEqual(box['outliers_sample'], [100.0])
        self.assertEqual(box['outlier_count'], 1)

    def test_constant_single_and_all_null_columns(self):
        frame = pl.DataFrame({'constant': [2, 2, 2], 'single': [5, None, None],
                              'empty': pl.Series([None] * 3, dtype=pl.Float64)})
        result = modeling.run_boxplot(frame, {'fields': frame.columns})
        self.assertEqual(result['meta']['fields_analyzed'], ['constant', 'single'])
        self.assertEqual(result['metrics'], {'total_fields': 2, 'total_outliers': 0})
        self.assertEqual([b['iqr'] for b in result['boxplots']], [0.0, 0.0])

    def test_outliers_keep_input_order_and_are_limited_to_fifty(self):
        frame = pl.DataFrame({'x': [0] * 300 + list(range(200, 260))})
        box = modeling.run_boxplot(frame, {'fields': ['x']})['boxplots'][0]
        self.assertEqual(box['outlier_count'], 60)
        self.assertEqual(box['outliers_sample'], list(range(200, 250)))

    def test_supported_numeric_types(self):
        for dtype in (pl.Int8, pl.Int16, pl.Int32, pl.Int64, pl.UInt8, pl.UInt16,
                      pl.UInt32, pl.UInt64, pl.Float32, pl.Float64):
            with self.subTest(dtype=dtype):
                box = modeling.run_boxplot(pl.DataFrame({'x': pl.Series([1, 2, 3], dtype=dtype)}),
                                           {'fields': ['x']})['boxplots'][0]
                self.assertEqual(box['median'], 2.0)

    def test_invalid_or_empty_fields_fail_explicitly(self):
        frame = pl.DataFrame({'label': ['a'], 'flag': [True]})
        with self.assertRaisesRegex(ValueError, 'Укажите хотя бы одно поле'):
            modeling.run_boxplot(frame, {})
        with self.assertLogs(modeling.__name__, level='WARNING'):
            with self.assertRaisesRegex(ValueError, 'Нет подходящих числовых полей'):
                modeling.run_boxplot(frame, {'fields': ['missing', 'label', 'flag']})
        with self.assertRaisesRegex(ValueError, 'Нет подходящих числовых полей'):
            modeling.run_boxplot(pl.DataFrame({'x': pl.Series([], dtype=pl.Float64)}), {'fields': ['x']})


class StatisticalModelContractTests(unittest.TestCase):
    def test_sarima_native_fit_matches_statsmodels_on_the_current_platform(self):
        from statsmodels.tsa.statespace.sarimax import SARIMAX

        _, frame, config = reference_cases()['sarima']
        values = frame.select(['day', 'value']).drop_nulls().sort('day')['value'].to_numpy().astype(float)
        fitted = SARIMAX(values, order=(1, 0, 0), seasonal_order=(1, 0, 0, 4)).fit(disp=False)
        self.assertTrue(fitted.mle_retvals['converged'])
        actual = modeling.run_sarima(frame, config)
        self.assertEqual(actual['params'], {str(i): round(float(value), 6)
                                          for i, value in enumerate(fitted.params)})
        self.assertEqual(actual['forecast'], [round(float(value), 6) for value in fitted.forecast(steps=5)])
        self.assertEqual(actual['residuals_sample'], [round(float(value), 6) for value in fitted.resid])
        self.assertEqual(actual['metrics'], {name: round(float(getattr(fitted, name)), 6)
                                            for name in ('aic', 'bic', 'hqic')})

    def test_linear_coefficients_recover_the_known_relationship_and_drop_incomplete_rows(self):
        result = modeling.run_linear_regression(regression_frame(),
                                                {'target_field': 'y', 'feature_fields': ['x', 'z']})
        for row, expected in zip(result['coefficients'], [2.0, 3.0, -1.5]):
            self.assertAlmostEqual(row['coef'], expected, delta=0.05)
        self.assertEqual([row['name'] for row in result['coefficients']], ['const', 'x', 'z'])
        self.assertGreater(result['metrics']['r_squared'], 0.99)
        self.assertEqual(result['meta']['n_observations'], 48)

    def test_linear_residuals_are_limited_without_limiting_training_rows(self):
        result = modeling.run_linear_regression(regression_frame(rows=240),
                                                {'target_field': 'y', 'feature_fields': ['x', 'z']})
        self.assertEqual(len(result['residuals_sample']), 200)
        self.assertEqual(result['meta']['n_observations'], 240)

    def test_time_models_sort_dates_drop_incomplete_rows_and_keep_forecast_size(self):
        for name in ('arima', 'sarima'):
            operation, frame, config = reference_cases()[name]
            with self.subTest(operation=name):
                function = getattr(modeling, operation)
                actual = function(frame, config)
                prepared = function(frame.drop_nulls().sort('day'), config)
                self.assertEqual(actual, prepared)
                self.assertEqual(actual['meta']['n_observations'], 64)
                self.assertEqual(len(actual['forecast']), 5)
                self.assertEqual(len(actual['residuals_sample']), 64)

    def test_time_model_defaults_keep_the_existing_orders(self):
        _, frame, _ = reference_cases()['arima']
        config = {'date_field': 'day', 'value_field': 'value'}
        result = modeling.run_arima(frame, config)
        self.assertEqual(result['order'], {'p': 1, 'd': 1, 'q': 1})
        self.assertEqual(len(result['forecast']), 10)

    def test_missing_source_columns_raise_instead_of_using_other_data(self):
        for name, (operation, frame, config) in reference_cases().items():
            if name == 'boxplot':
                continue
            with self.subTest(operation=name):
                with self.assertRaises(pl.exceptions.ColumnNotFoundError):
                    getattr(modeling, operation)(frame.clear().drop(frame.columns[0]), config)


class ModelingIsolationTests(unittest.TestCase):
    def test_modeling_executes_without_framework_and_domain_packages(self):
        script = '''import importlib.abc,sys
class BlockFramework(importlib.abc.MetaPathFinder):
    def find_spec(self, fullname, path=None, target=None):
        if fullname.split('.')[0] in {'django','celery','rest_framework','modules'}:
            raise ImportError('Framework/domain import attempted: '+fullname)
sys.meta_path.insert(0,BlockFramework())
from src.core.analytics import modeling
from src.core.analytics.tests.modeling_cases import reference_cases
assert 'statsmodels' not in sys.modules
for operation,frame,config in reference_cases().values():
    assert getattr(modeling,operation)(frame,config)['model_type']
'''
        environment = {**os.environ, 'PYTHONPATH': str(Path(__file__).resolve().parents[4])}
        result = subprocess.run([sys.executable, '-c', script], env=environment,
                                capture_output=True, text=True, timeout=60)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
