"""Пагинация журнала аудита без COUNT(*) по всей таблице."""

from rest_framework.pagination import BasePagination
from rest_framework.response import Response


class AuditPagination(BasePagination):
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

        offset = (page_number - 1) * page_size
        slice_end = offset + page_size + 1
        page_items = list(queryset[offset:slice_end])
        self.has_next = len(page_items) > page_size
        self.has_previous = page_number > 1
        self.page_number = page_number
        self.page_size = page_size
        self.request = request
        return page_items[:page_size]

    def get_paginated_response(self, data):
        return Response({
            'results': data,
            'page': self.page_number,
            'page_size': self.page_size,
            'has_next': self.has_next,
            'has_previous': self.has_previous,
        })

    def get_paginated_response_schema(self, schema):
        return {
            'type': 'object',
            'properties': {
                'results': schema,
                'page': {'type': 'integer'},
                'page_size': {'type': 'integer'},
                'has_next': {'type': 'boolean'},
                'has_previous': {'type': 'boolean'},
            },
        }
