"""Calendar range selection without source queries or timezone conversion."""
from datetime import date, datetime

DATE_TRUNC_UNITS = frozenset({'day', 'week', 'month', 'quarter', 'year'})


def coerce_to_date(value):
    if value is None:
        return None
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    text = str(value).strip()
    if not text:
        return None
    if len(text) >= 10:
        try:
            return datetime.strptime(text[:10], '%Y-%m-%d').date()
        except ValueError:
            pass
    try:
        return datetime.fromisoformat(text.replace('Z', '+00:00')).date()
    except (TypeError, ValueError):
        return None


def date_span_days(min_val, max_val):
    min_date = coerce_to_date(min_val)
    max_date = coerce_to_date(max_val)
    if min_date is None or max_date is None:
        return 0
    return max(0, (max_date - min_date).days)


def pick_date_trunc_unit(min_val, max_val):
    span = date_span_days(min_val, max_val)
    if span <= 31:
        return 'day'
    if span <= 366:
        return 'month'
    if span <= 1095:
        return 'quarter'
    return 'year'
