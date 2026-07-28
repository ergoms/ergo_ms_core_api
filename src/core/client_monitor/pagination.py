"""Пагинация списков мониторинга клиентов."""

from math import ceil

from rest_framework.pagination import BasePagination
from rest_framework.response import Response


class ClientMonitorPagination(BasePagination):
    page_size = 50
    page_query_param = 'page'
    page_size_query_param = 'page_size'
    max_page_size = 200

    def paginate_queryset(self, queryset, request, view=None):
        try:
            page_size = int(request.query_params.get(self.page_size_query_param, self.page_size))
        except (TypeError, ValueError):
            page_size = self.page_size
        page_size = max(1, min(page_size, self.max_page_size))

        try:
            page_number = int(request.query_params.get(self.page_query_param, 1))
        except (TypeError, ValueError):
            page_number = 1
        page_number = max(1, page_number)

        self.total_count = queryset.count()
        total_pages = max(1, ceil(self.total_count / page_size)) if self.total_count else 1
        if page_number > total_pages:
            page_number = total_pages

        offset = (page_number - 1) * page_size
        page_items = list(queryset[offset:offset + page_size])

        self.has_next = page_number < total_pages
        self.has_previous = page_number > 1
        self.page_number = page_number
        self.page_size = page_size
        self.total_pages = total_pages
        return page_items

    def get_paginated_response(self, data):
        return Response({
            'results': data,
            'count': self.total_count,
            'page': self.page_number,
            'page_size': self.page_size,
            'total_pages': self.total_pages,
            'has_next': self.has_next,
            'has_previous': self.has_previous,
        })
