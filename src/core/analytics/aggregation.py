"""Scalar aggregation compatibility helpers; no queries or domain objects."""
import math


def json_compatible_value(value):
    """NaN и бесконечность в файле — пустое значение, как NULL в SQL. JSON их не принимает."""
    if isinstance(value, float) and (math.isnan(value) or math.isinf(value)):
        return None
    return value


def finish_aggregate(acc, aggregation):
    if aggregation == 'count':
        return acc[0]
    if aggregation == 'ucount':
        return len(acc)
    if aggregation == 'sum':
        return json_compatible_value(acc[0]) if acc[1] else None
    if aggregation == 'avg':
        if not acc[1]:
            return None
        return json_compatible_value(acc[0] / acc[1])
    return json_compatible_value(acc[0])


def parse_bin_parameters(agg_l):
    """Parse the existing bin:N:min:max notation and its bounded count fallback."""
    parts = agg_l.split(':')
    try:
        n = int(parts[1]) if len(parts) > 1 else 20
    except (TypeError, ValueError):
        n = 20
    n = max(1, min(n, 200))

    min_v = max_v = None
    if len(parts) > 3:
        try:
            min_v = float(parts[2])
            max_v = float(parts[3])
        except (TypeError, ValueError):
            min_v = max_v = None

    if min_v is None or max_v is None or min_v >= max_v:
        return None
    return n, min_v, max_v
