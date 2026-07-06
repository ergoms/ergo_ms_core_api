"""Общие helpers для инкрементального polling по id."""


def parse_after_id_value(raw):
    """Вернуть int id или None, если значение отсутствует или невалидно."""
    if raw is None or raw == '':
        return None
    try:
        return int(raw)
    except (TypeError, ValueError):
        return None


def apply_after_id(queryset, request, *, param='after_id'):
    """Фильтр `id__gt` по query-параметру; при невалидном значении queryset не меняется."""
    after_id = parse_after_id_value(request.query_params.get(param))
    if after_id is None:
        return queryset
    return queryset.filter(id__gt=after_id)
