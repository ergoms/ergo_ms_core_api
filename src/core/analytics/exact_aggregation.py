"""Exact decimal aggregation of prepared tables, independent of BI and Django.

Specs describe output aliases, source column indices, types and operations.
The caller owns source access, SQL, date/bin transformations and collation.
"""
import math
import re
from decimal import Decimal, InvalidOperation, ROUND_HALF_EVEN, ROUND_HALF_UP, localcontext


OPERATIONS = frozenset({'none', 'sum', 'avg', 'count', 'ucount', 'min', 'max'})
_CLEAN_NUMBER = re.compile(r'[^0-9.\-]')


def decimal_number(value, *, permissive=False):
    if value is None or isinstance(value, bool):
        return None
    text = str(value).strip().replace(',', '.')
    if permissive and isinstance(value, str):
        text = _CLEAN_NUMBER.sub('', text)
    try:
        result = Decimal(text)
    except InvalidOperation:
        if permissive or not text:
            return None
        raise ValueError('Invalid numeric source value') from None
    return result if result.is_finite() else None


def cast_scalar(value, kind):
    if kind not in ('integer', 'float'):
        return None if isinstance(value, float) and not math.isfinite(value) else value
    if isinstance(value, bool):
        raise ValueError('Invalid numeric source value')
    number = decimal_number(value)
    if number is not None and kind == 'integer':
        number = int(number.to_integral_value(rounding=ROUND_HALF_UP))
        if not -(2**63) <= number < 2**63:
            raise ValueError('Integer source value is out of range')
    return number


def exact_sum(values):
    numbers = [value for value in values if value is not None]
    if not numbers:
        return None
    # Enough digits for the largest coefficient, fractional tail and carries.
    precision = max(v.adjusted() for v in numbers) - min(v.as_tuple().exponent for v in numbers)
    with localcontext() as context:
        context.prec = max(28, precision + len(str(len(numbers))) + 2)
        return sum(numbers, Decimal(0))


def round_mean(value):
    """Common HALF_EVEN mean: >=28 significant and >=16 fractional digits."""
    if value is None:
        return None
    with localcontext() as context:
        context.prec = max(28, value.adjusted() + 1 + 16)
        context.rounding = ROUND_HALF_EVEN
        return +value


def aggregate_values(values, operation):
    nonnull = [value for value in values if value is not None]
    if operation == 'count':
        return len(nonnull)
    if operation == 'ucount':
        return len({_typed_key(value) for value in nonnull})
    if operation in ('min', 'max'):
        return (min if operation == 'min' else max)(nonnull) if nonnull else None
    numbers = [number for value in values
               if (number := decimal_number(value, permissive=True)) is not None]
    total = exact_sum(numbers)
    if operation == 'sum' or total is None:
        return total
    if operation != 'avg':
        raise ValueError('Unsupported aggregation: ' + operation)
    with localcontext() as context:
        context.prec = max(64, total.adjusted() + 1 + 64, len(total.as_tuple().digits) + 64)
        context.rounding = ROUND_HALF_EVEN
        return round_mean(total / len(numbers))


def _typed_key(value):
    if value is None:
        return ('null',)
    if isinstance(value, (int, float, Decimal)) and not isinstance(value, bool):
        return ('number', Decimal(str(value)))
    return (type(value).__name__, value)


def aggregate_table(rows, specs):
    """Group with typed tuples, retaining first occurrence order and SQL NULLs."""
    if not specs:
        return []
    if any(spec['aggregation'] not in OPERATIONS for spec in specs):
        raise ValueError('Unsupported table aggregation')
    grouped = [s for s in specs if s['aggregation'] == 'none']
    measures = [s for s in specs if s['aggregation'] != 'none']
    buckets = {} if grouped else {(): ([], {s['output']: [] for s in measures})}
    for row in rows:
        values = {s['output']: cast_scalar(row[s['index']] if s['index'] < len(row) else None,
                                          s.get('type')) for s in specs}
        group = [values[s['output']] for s in grouped]
        key = tuple(_typed_key(value) for value in group)
        if key not in buckets:
            buckets[key] = (group, {s['output']: [] for s in measures})
        for spec in measures:
            buckets[key][1][spec['output']].append(values[spec['output']])
    result = []
    for group, values in buckets.values():
        item = {s['output']: value for s, value in zip(grouped, group)}
        item.update({s['output']: aggregate_values(values[s['output']], s['aggregation']) for s in measures})
        result.append(item)
    return result


def transport_value(value):
    """JSON-safe decimal strings; preserve legacy safe integer/string types."""
    if isinstance(value, Decimal):
        if not value.is_finite():
            return None
        text = format(value, 'f')
        text = text.rstrip('0').rstrip('.') if '.' in text else text
        return '0' if value == 0 else text
    if isinstance(value, int) and not isinstance(value, bool) and abs(value) > 2**53 - 1:
        return str(value)
    if isinstance(value, float) and not math.isfinite(value):
        return None
    return value
