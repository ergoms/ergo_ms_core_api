"""Calendar selection boundaries used by database aggregation adapters."""
from datetime import date, datetime, timedelta, timezone
import unittest

from src.core.analytics.date_grouping import DATE_TRUNC_UNITS, coerce_to_date, date_span_days, pick_date_trunc_unit


class DateGroupingTests(unittest.TestCase):
    def test_native_and_iso_dates(self):
        for value in (date(2024, 2, 29), datetime(2024, 2, 29, 23), '2024-02-29',
                      '2024-02-29T23:30:00Z', '2024-02-29T23:30:00+03:00'):
            with self.subTest(value=value):
                self.assertEqual(coerce_to_date(value), date(2024, 2, 29))

    def test_offset_dates_keep_the_existing_wall_calendar_day(self):
        value = datetime(2024, 1, 1, 1, tzinfo=timezone(timedelta(hours=3)))
        self.assertEqual(coerce_to_date(value), date(2024, 1, 1))

    def test_missing_and_invalid_dates_are_ignored(self):
        for value in (None, '', '   ', 'invalid', '2023-02-29', 42):
            with self.subTest(value=value):
                self.assertIsNone(coerce_to_date(value))

    def test_span_handles_leap_days_missing_and_reversed_ranges(self):
        self.assertEqual(date_span_days('2024-02-28', '2024-03-01'), 2)
        self.assertEqual(date_span_days('2024-03-01', '2024-02-28'), 0)
        self.assertEqual(date_span_days(None, '2024-01-01'), 0)

    def test_auto_granularity_thresholds(self):
        start = date(2020, 1, 1)
        for span, unit in [(0, 'day'), (31, 'day'), (32, 'month'), (366, 'month'),
                            (367, 'quarter'), (1095, 'quarter'), (1096, 'year')]:
            with self.subTest(span=span):
                self.assertEqual(pick_date_trunc_unit(start, start + timedelta(days=span)), unit)

    def test_supported_calendar_units_are_explicit(self):
        self.assertEqual(DATE_TRUNC_UNITS, frozenset({'day', 'week', 'month', 'quarter', 'year'}))
