"""Contracts for the row-oriented boundary of prepared DataFrames."""
from datetime import date, datetime, timezone
from decimal import Decimal
import os
from pathlib import Path
import subprocess
import sys
import unittest

import polars as pl
from polars.testing import assert_frame_equal

from src.core.analytics.tables import frame_to_rows, rows_to_frame


class TableConversionTests(unittest.TestCase):
    def test_column_and_row_order_survive_a_round_trip(self):
        columns, rows = ['b', 'a'], [[2, 'second'], [1, 'first']]
        frame = rows_to_frame(columns, rows)
        self.assertEqual(frame_to_rows(frame), (columns, rows))
        self.assertEqual(columns, ['b', 'a'])
        self.assertEqual(rows, [[2, 'second'], [1, 'first']])

    def test_short_rows_are_padded_and_extra_values_are_ignored(self):
        frame = rows_to_frame(['a', 'b'], [[1], [2, 'value', 'extra'], []])
        self.assertEqual(frame_to_rows(frame), (['a', 'b'], [[1, None], [2, 'value'], [None, None]]))

    def test_empty_and_missing_headers_keep_the_previous_shape(self):
        for columns, rows, expected_columns in ((None, None, []), ([], [[1]], []),
                                                 (['a', 'b'], [], ['a', 'b'])):
            with self.subTest(columns=columns):
                frame = rows_to_frame(columns, rows)
                self.assertEqual(frame.shape, (0, len(expected_columns)))
                self.assertEqual(frame_to_rows(frame), (expected_columns, []))
                self.assertTrue(all(dtype == pl.Null for dtype in frame.dtypes))

    def test_tuples_and_unicode_names_are_supported(self):
        frame = rows_to_frame(('сумма', 'Город'), ((1, 'Москва'), (None, 'Казань')))
        self.assertEqual(frame_to_rows(frame), (['сумма', 'Город'], [[1, 'Москва'], [None, 'Казань']]))

    def test_native_numeric_temporal_and_boolean_values_keep_their_types(self):
        moment = datetime(2024, 1, 1, tzinfo=timezone.utc)
        frame = rows_to_frame(['day', 'at', 'money', 'flag'],
                              [[date(2024, 1, 1), moment, Decimal('1.25'), True], [None] * 4])
        self.assertEqual(frame.dtypes, [pl.Date, pl.Datetime('us', 'UTC'), pl.Decimal(precision=38, scale=2), pl.Boolean])
        self.assertEqual(frame_to_rows(frame)[1][0], [date(2024, 1, 1), moment, Decimal('1.25'), True])

    def test_serializing_a_frame_does_not_mutate_it(self):
        frame = pl.DataFrame({'x': [1.0, None], 'name': ['a', 'b']})
        original = frame.clone()
        columns, rows = frame_to_rows(frame)
        rows[0][0] = -10
        columns.append('extra')
        assert_frame_equal(frame, original)

    def test_incompatible_values_keep_polars_validation(self):
        with self.assertRaises(TypeError):
            rows_to_frame(['x'], [[1], ['invalid']])


class TableProfileIsolationTests(unittest.TestCase):
    def test_conversions_and_profiles_do_not_import_application_frameworks(self):
        script = '''import importlib.abc,sys,json
class BlockFramework(importlib.abc.MetaPathFinder):
    def find_spec(self, fullname, path=None, target=None):
        if fullname.split('.')[0] in {'django','celery','rest_framework','modules','sqlalchemy'}:
            raise ImportError('Framework/domain import attempted: '+fullname)
sys.meta_path.insert(0,BlockFramework())
from src.core.analytics.tables import rows_to_frame,frame_to_rows
from src.core.analytics.eda import compute_summary
from src.core.analytics.profiling import summary_from_entries,summary_from_aggregate_row
frame=rows_to_frame(['x'],[[1],[2],[None]])
assert frame_to_rows(frame)[1]==[[1],[2],[None]]
assert summary_from_entries([('x','x')],compute_summary(frame),3)[0]['mean']==1.5
assert summary_from_aggregate_row([('x',True)],(3,2,2,1,2,1.5,0.70710678))[0]==3
assert not {'statsmodels','torch','django','celery','sqlalchemy'} & sys.modules.keys()
'''
        environment = {**os.environ, 'PYTHONPATH': str(Path(__file__).resolve().parents[4])}
        result = subprocess.run([sys.executable, '-c', script], env=environment,
                                capture_output=True, text=True, timeout=30)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
