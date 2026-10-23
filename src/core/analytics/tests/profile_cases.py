"""Reference data for column profiles, without any application models."""
from decimal import Decimal


def aggregate_cases():
    return {
        'mixed': ([('city', False), ('amount', True)], (10, 10, 3, 8, 7, 1, 9, 4.5, 2.0)),
        'empty': ([], []),
        'all_null': ([('x', True)], (5, 0, 0, None, None, None, None)),
        'no_rows': ([('x', True), ('label', False)], (0, 0, 0, None, None, None, None, 0, 0)),
        'decimal': ([('x', True)], (3, 2, 2, Decimal('0.1'), Decimal('0.3'), Decimal('0.2'), Decimal('0.1414213562373095'))),
        'non_finite': ([('x', True)], ('5', '3', 'invalid', float('nan'), float('inf'), -float('inf'), True)),
    }


def entry_cases():
    return {
        'aliases': ([('amount', 'Amount'), ('city', 'City')], [
            {'name': 'Amount', 'nulls': 2, 'null_pct': 20, 'unique': 7,
             'min': 1, 'max': 9, 'mean': 4.5, 'std': 2},
            {'name': 'City', 'nulls': 1, 'null_pct': 10, 'unique': 3},
        ], 10),
        'fallback_and_missing': ([('x', 'old'), ('missing', 'Absent')], [
            {'name': 'x', 'unique': '2', 'nulls': '1', 'null_pct': '25.0', 'mean': Decimal('1.25')},
        ], 4),
        'duplicates': ([('renamed', 'x'), ('x', 'x')], [
            {'name': 'x', 'unique': 1}, {'name': 'x', 'unique': 2},
        ], 2),
        'invalid_values': ([('x', 'x')], [None, 42, {}, {'name': ''}, {
            'name': 'x', 'nulls': 'invalid', 'null_pct': float('nan'), 'unique': None,
            'min': True, 'max': float('inf'), 'mean': 'invalid', 'std': -float('inf'),
        }], 3),
        'empty': ([('x', 'x')], [], 0),
    }
