"""Contracts for shared aggregate finalization and histogram parameters."""
from copy import deepcopy
from decimal import Decimal
import os
from pathlib import Path
import subprocess
import sys
import unittest

from src.core.analytics.aggregation import finish_aggregate, json_compatible_value, parse_bin_parameters


class AggregateFinalizationTests(unittest.TestCase):
    def test_count_and_distinct_count(self):
        self.assertEqual(finish_aggregate([3], 'count'), 3)
        self.assertEqual(finish_aggregate({'a', 'b'}, 'ucount'), 2)

    def test_sum_and_average_keep_decimal_precision(self):
        self.assertEqual(finish_aggregate([Decimal('9007199254740993'), 1], 'sum'), Decimal('9007199254740993'))
        self.assertEqual(finish_aggregate([Decimal('0.3'), 2], 'avg'), Decimal('0.15'))

    def test_empty_states_keep_sql_null_and_zero_semantics(self):
        for operation in ('sum', 'avg'):
            self.assertIsNone(finish_aggregate([Decimal(0), 0], operation))
        self.assertEqual(finish_aggregate([0], 'count'), 0)
        self.assertEqual(finish_aggregate(set(), 'ucount'), 0)
        for operation in ('min', 'max'):
            self.assertIsNone(finish_aggregate([None, False], operation))

    def test_extrema_keep_the_original_value_type(self):
        self.assertEqual(finish_aggregate(['Москва', True], 'min'), 'Москва')
        self.assertIs(type(finish_aggregate([7, True], 'max')), int)

    def test_finalization_does_not_change_states(self):
        for operation, state in [('sum', [Decimal('1.25'), 2]), ('ucount', {1, 2}), ('max', [4, True])]:
            original = deepcopy(state)
            finish_aggregate(state, operation)
            self.assertEqual(state, original)

    def test_non_finite_python_floats_are_null(self):
        for value in (float('nan'), float('inf'), -float('inf')):
            self.assertIsNone(json_compatible_value(value))
        for value in (None, True, 'value', Decimal('1.25'), 0.0):
            self.assertEqual(json_compatible_value(value), value)


class BinParameterTests(unittest.TestCase):
    def test_negative_and_fractional_bounds(self):
        self.assertEqual(parse_bin_parameters('bin:20:-1.5:99.7'), (20, -1.5, 99.7))

    def test_count_is_bounded_between_one_and_two_hundred(self):
        for text, expected in [('0', 1), ('-10', 1), ('999', 200), ('invalid', 20), ('2.5', 20)]:
            with self.subTest(count=text):
                self.assertEqual(parse_bin_parameters(f'bin:{text}:0:10')[0], expected)

    def test_missing_or_reversed_ranges_preserve_the_fallback(self):
        for value in ('bin', 'bin:10', 'bin:10:0', 'bin:10:5:5', 'bin:10:10:0', 'bin:10:x:10'):
            with self.subTest(value=value):
                self.assertIsNone(parse_bin_parameters(value))

    def test_fractional_boundaries_are_not_rounded(self):
        self.assertEqual(parse_bin_parameters('bin:3:0.125:0.875'), (3, 0.125, 0.875))


class ScalarAggregationIsolationTests(unittest.TestCase):
    def test_scalar_helpers_need_no_framework_database_or_dataframe_runtime(self):
        script = '''import importlib.abc,sys
class BlockRuntime(importlib.abc.MetaPathFinder):
    def find_spec(self,fullname,path=None,target=None):
        if fullname.split('.')[0] in {'django','celery','modules','sqlalchemy','polars','numpy','statsmodels'}:
            raise ImportError('Unexpected runtime import: '+fullname)
sys.meta_path.insert(0,BlockRuntime())
from src.core.analytics.aggregation import finish_aggregate,parse_bin_parameters
from src.core.analytics.date_grouping import pick_date_trunc_unit
assert finish_aggregate([3,2],'avg')==1.5
assert parse_bin_parameters('bin:4:-10:10')==(4,-10.,10.)
assert pick_date_trunc_unit('2024-01-01','2024-01-15')=='day'
'''
        environment = {**os.environ, 'PYTHONPATH': str(Path(__file__).resolve().parents[4])}
        result = subprocess.run([sys.executable, '-c', script], env=environment,
                                capture_output=True, text=True, timeout=30)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
