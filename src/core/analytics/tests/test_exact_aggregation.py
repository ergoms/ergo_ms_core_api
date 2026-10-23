"""Plain table aggregation has the same keys and decimal semantics as SQL."""
from decimal import Decimal, ROUND_UP, localcontext
from unittest import TestCase

from src.core.analytics.exact_aggregation import aggregate_table, round_mean, transport_value


class ExactAggregationTests(TestCase):
    def specs(self, operation='sum'):
        return [{'output': 'x', 'index': 0, 'aggregation': 'none', 'type': 'string'},
                {'output': 'value', 'index': 1, 'aggregation': operation, 'type': 'float'}]

    def test_null_empty_and_placeholder_do_not_merge(self):
        self.assertEqual(aggregate_table([[None, 1], ['', 2], ['—', 3]], self.specs()),
                         [{'x': None, 'value': 1}, {'x': '', 'value': 2}, {'x': '—', 'value': 3}])

    def test_decimal_sum_has_no_binary_or_context_rounding(self):
        rows = [['A', '9007199254740993000000000000000'], ['A', '0.01']]
        result = aggregate_table(rows, self.specs())[0]['value']
        self.assertEqual(result, Decimal('9007199254740993000000000000000.01'))

    def test_average_ignores_null_and_rounds_consistently(self):
        self.assertEqual(aggregate_table([['A', 1], ['A', 0], ['A', 0], ['A', None]],
                                         self.specs('avg'))[0]['value'],
                         Decimal('0.3333333333333333333333333333'))
        self.assertEqual(round_mean(Decimal('9007199254740993000000000000000.125')),
                         Decimal('9007199254740993000000000000000.125'))
        with localcontext() as context:
            context.prec = 2
            context.rounding = ROUND_UP
            self.assertEqual(aggregate_table([['A', 1], ['A', 0], ['A', 0]], self.specs('avg'))[0]['value'],
                             Decimal('0.3333333333333333333333333333'))

    def test_empty_global_and_all_null(self):
        for operation, expected in [('sum', None), ('avg', None), ('min', None),
                                    ('max', None), ('count', 0), ('ucount', 0)]:
            spec = self.specs(operation)[1:]
            self.assertEqual(aggregate_table([], spec), [{'value': expected}])
            self.assertEqual(aggregate_table([['A', None]], spec), [{'value': expected}])

    def test_counts_and_extrema(self):
        for operation, expected in [('sum', 6), ('avg', 2), ('count', 3),
                                    ('ucount', 2), ('min', -2), ('max', 4)]:
            result = aggregate_table([['A', 4], ['A', None], ['A', 4], ['A', -2]], self.specs(operation))
            self.assertEqual(result, [{'x': 'A', 'value': expected}])

    def test_integer_cast_rounds_away_from_zero_and_rejects_overflow(self):
        specs = [{'output': 'x', 'index': 0, 'aggregation': 'none', 'type': 'integer'}]
        self.assertEqual(aggregate_table([['1,5'], ['-1.5'], ['NaN']], specs),
                         [{'x': 2}, {'x': -2}, {'x': None}])
        with self.assertRaises(ValueError):
            aggregate_table([[str(2**63)]], specs)

    def test_transport_keeps_decimal_and_unsafe_integer_exact(self):
        self.assertEqual(transport_value(Decimal('9007199254740993.01')), '9007199254740993.01')
        self.assertEqual(transport_value(2**53), str(2**53))
        self.assertEqual(transport_value(42), 42)
