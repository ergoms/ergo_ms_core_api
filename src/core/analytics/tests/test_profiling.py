"""Original profile results and explicit normalization contracts."""
from copy import deepcopy
import json
import math
from pathlib import Path
import unittest

from src.core.analytics.profiling import summary_from_aggregate_row, summary_from_entries
from .profile_cases import aggregate_cases, entry_cases


class ProfileReferenceTests(unittest.TestCase):
    def setUp(self):
        self.reference = json.loads((Path(__file__).with_name('fixtures') / 'profiles.json').read_text(encoding='utf-8'))

    def test_aggregate_results_match_the_frozen_original(self):
        for name, (specs, row) in aggregate_cases().items():
            with self.subTest(case=name):
                actual = summary_from_aggregate_row(specs, row)
                self.assertEqual(json.loads(json.dumps(actual, allow_nan=False)), self.reference['aggregates'][name])

    def test_entry_results_match_the_frozen_original(self):
        for name, (columns, entries, total) in entry_cases().items():
            with self.subTest(case=name):
                actual = summary_from_entries(columns, entries, total)
                self.assertEqual(actual, self.reference['entries'][name])
                json.dumps(actual, allow_nan=False)

    def test_input_structures_are_not_modified(self):
        columns, entries, total = entry_cases()['aliases']
        before = deepcopy((columns, entries))
        summary_from_entries(columns, entries, total)
        self.assertEqual((columns, entries), before)


class ProfileContractTests(unittest.TestCase):
    def test_null_percentage_and_aggregate_distinct_counts_are_preserved(self):
        total, summary = summary_from_aggregate_row([('x', True)], (3, 2, 2, 1, 2, 1.5, 0.70710678))
        self.assertEqual(total, 3)
        self.assertEqual(summary[0]['nulls'], 1)
        self.assertEqual(summary[0]['null_pct'], 33.33)
        self.assertEqual(summary[0]['unique'], 2)
        self.assertEqual(summary[0]['std'], 0.70710678)

    def test_alias_priority_and_field_order_are_preserved(self):
        entries = [{'name': 'source', 'mean': 1}, {'name': 'display', 'mean': 2}]
        result = summary_from_entries([('display', 'source'), ('source', 'absent')], entries, 2)
        self.assertEqual([(e['name'], e['mean']) for e in result], [('display', 1.0), ('source', 1.0)])

    def test_non_finite_and_boolean_values_are_not_serialized_as_numeric_metrics(self):
        for value in (True, False, math.nan, math.inf, -math.inf, 'invalid'):
            with self.subTest(value=value):
                result = summary_from_entries([('x', 'x')], [{'name': 'x', 'mean': value}], 1)
                self.assertIsNone(result[0]['mean'])
                json.dumps(result, allow_nan=False)

    def test_missing_and_duplicate_entries_keep_the_existing_rules(self):
        result = summary_from_entries([('x', 'x'), ('missing', 'none')],
                                      [{'name': 'x', 'unique': 1}, {'name': 'x', 'unique': 2}], 2)
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]['unique'], 2)

    def test_malformed_aggregate_rows_fail_instead_of_returning_a_partial_profile(self):
        with self.assertRaises(IndexError):
            summary_from_aggregate_row([('x', True)], (3, 2))
