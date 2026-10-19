"""Предел id, которые поиск подставляет в queryset, и страница из query."""

from __future__ import annotations

from math import ceil

SEARCH_ID_LIMIT = 1000


def page_from_request(request, *, default_page_size: int, max_page_size: int) -> tuple[int, int]:
    """page и page_size запроса, не шире лимита поиска и пагинации списка."""
    params = getattr(request, 'query_params', None)
    raw_page = params.get('page') if params is not None else None
    raw_size = params.get('page_size') if params is not None else None
    try:
        page_number = int(raw_page or 1)
    except (TypeError, ValueError):
        page_number = 1
    try:
        size = int(raw_size if raw_size not in (None, '') else default_page_size)
    except (TypeError, ValueError):
        size = default_page_size
    page_number = max(1, page_number)
    size = max(1, min(size, max_page_size, SEARCH_ID_LIMIT))
    return page_number, size


def take_prefetched_search_page(paginator, queryset, request, view):
    """Страница, уже полученная из поиска: не режем queryset второй раз.

    View ставит ``_search_total`` — полное число совпадений, а queryset содержит
    только id текущей страницы. Возвращает None, если поиск страницу не готовил.
    """
    if view is None:
        return None
    total = getattr(view, '_search_total', None)
    if total is None:
        return None

    try:
        page_size = int(request.query_params.get(paginator.page_size_query_param, paginator.page_size))
    except (TypeError, ValueError):
        page_size = paginator.page_size
    page_size = max(1, min(page_size, paginator.max_page_size))

    try:
        page_number = int(request.query_params.get(paginator.page_query_param, 1))
    except (TypeError, ValueError):
        page_number = 1
    page_number = max(1, page_number)

    total_count = int(total)
    total_pages = max(1, ceil(total_count / page_size)) if total_count else 1
    paginator.total_count = total_count
    paginator.has_next = page_number < total_pages
    paginator.has_previous = page_number > 1
    paginator.page_number = page_number
    paginator.page_size = page_size
    paginator.total_pages = total_pages
    paginator.request = request
    return list(queryset)
