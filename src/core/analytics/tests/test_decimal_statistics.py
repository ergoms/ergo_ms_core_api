"""PostgreSQL numeric columns are quantitative inputs to statistical operations."""
from decimal import Decimal
import json
import unittest

import polars as pl
from polars.testing import assert_frame_equal

from src.core.analytics import eda, modeling


class DecimalStatisticsTests(unittest.TestCase):
    def frame(self):
        return pl.DataFrame({'amount': pl.Series([Decimal(value) if value is not None else None
                              for value in ('0', '1', '2', '3', '100', None)], dtype=pl.Decimal(38, 2))})

    def test_summary_keeps_decimal_metadata_and_computes_numeric_statistics(self):
        result = eda.compute_summary(self.frame())[0]
        self.assertEqual((result['count'], result['nulls'], result['unique']), (6, 1, 6))
        self.assertEqual(result['dtype'], 'Decimal(precision=38, scale=2)')
        self.assertEqual((result['min'], result['max'], result['median']), (0.0, 100.0, 2.0))
        self.assertAlmostEqual(result['mean'], 21.2)
        self.assertAlmostEqual(result['std'], 44.06472512112154)
        json.dumps(result, allow_nan=False)

    def test_distribution_is_a_histogram_counting_every_non_null_number(self):
        result = eda.compute_distributions(self.frame())
        self.assertNotIn('amount', result['categorical'])
        self.assertEqual(sum(result['numeric']['amount']['counts']), 5)
        json.dumps(result, allow_nan=False)

    def test_decimal_columns_participate_in_mixed_numeric_correlations(self):
        frame = pl.DataFrame({'decimal': pl.Series([Decimal('1.25'), Decimal('2.50'), Decimal('3.75'), None],
                                                    dtype=pl.Decimal(38, 2)),
                              'float': [2.5, 5.0, 7.5, None], 'flag': [True, False, True, False]})
        result = eda.compute_correlations(frame)
        self.assertEqual(result['fields'], ['decimal', 'float'])
        self.assertEqual(result['matrix'], [[1.0, 1.0], [1.0, 1.0]])

    def test_outliers_use_the_same_tukey_fences_as_float_columns(self):
        self.assertEqual(eda.compute_outliers(self.frame()),
                         eda.compute_outliers(self.frame().with_columns(pl.col('amount').cast(pl.Float64))))
        self.assertEqual(eda.compute_outliers(self.frame())[0]['count'], 1)

    def test_boxplot_accepts_decimal_fields_and_keeps_the_numeric_contract(self):
        result = modeling.run_boxplot(self.frame(), {'fields': ['amount']})
        self.assertEqual(result['boxplots'][0]['outliers_sample'], [100.0])
        self.assertEqual(result['meta']['n_observations'], 6)
        json.dumps(result, allow_nan=False)

    def test_null_empty_and_input_immutability(self):
        frame = self.frame()
        before = frame.clone()
        for source in (frame, pl.DataFrame({'amount': pl.Series([None], dtype=pl.Decimal(38, 2))}), frame.clear()):
            for function in (eda.compute_summary, eda.compute_distributions, eda.compute_correlations, eda.compute_outliers):
                json.dumps(function(source), allow_nan=False)
        assert_frame_equal(frame, before)
        self.assertIsNone(eda.compute_summary(frame.clear())[0]['mean'])
