from rest_framework import generics, permissions
from rest_framework.permissions import IsAuthenticated

from src.core.bi_analysis.bi_charts.models import Chart
from src.core.bi_analysis.bi_charts.serializers import ChartSerializer

from rest_framework.decorators import api_view, permission_classes
from rest_framework.response import Response
from rest_framework import status

from django.shortcuts import get_object_or_404

from src.core.bi_analysis.bi_charts.methods import get_rows_for_chart

from rest_framework.views import APIView

from src.core.bi_analysis.bi_charts.models import Chart
from src.core.bi_analysis.bi_charts.serializers import ChartSerializer
from src.core.bi_analysis.bi_datasets.models import Dataset


class IsChartOwnerOrReadOnly(permissions.BasePermission):
    """GET/HEAD/OPTIONS — любой авторизованный; PUT/PATCH/DELETE — только владелец."""

    def has_object_permission(self, request, view, obj):
        if request.method in permissions.SAFE_METHODS:
            return True
        if obj.owner_id is None:
            return False
        return obj.owner_id == request.user.id


class ChartListCreateView(generics.ListCreateAPIView):
    queryset = Chart.objects.all()
    serializer_class = ChartSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        user = self.request.user
        if not user.is_authenticated:
            return self.queryset.none()
        return self.queryset.filter(owner=user)

    def perform_create(self, serializer):
        serializer.save(owner=self.request.user)

class ChartDetailView(generics.RetrieveUpdateDestroyAPIView):
    """
    GET: любой авторизованный (просмотр в т.ч. чужого чарта).
    PUT/PATCH/DELETE: только владелец.
    """
    queryset = Chart.objects.all().select_related('dataset')
    serializer_class = ChartSerializer
    permission_classes = [IsAuthenticated, IsChartOwnerOrReadOnly]

    def get_queryset(self):
        if getattr(self, 'swagger_fake_view', False):
            return Chart.objects.none()
        return Chart.objects.all().select_related('dataset')
    
    
_VIRTUAL_MEASURE_IDS = frozenset({'__measure_names__', '__measure_values__'})


def _filter_virtual_fields(fields):
    return [
        f for f in fields
        if (f.get('id') or f.get('name')) not in _VIRTUAL_MEASURE_IDS
    ]


class ChartRowsAPIView(APIView):
    permission_classes = [IsAuthenticated]
    def get(self, request, pk):
        chart = get_object_or_404(Chart, pk=pk)
        dataset = chart.dataset

        params = chart.params or {}
        chart_fields = []
        for section in ('x', 'y', 'y2', 'color', 'labels', 'sort', 'value', 'indicators', 'category', 'columns'):
            if section in params:
                section_fields = params[section]
                if isinstance(section_fields, list):
                    chart_fields.extend(_filter_virtual_fields(section_fields))
                elif section_fields and (section_fields.get('id') or section_fields.get('name')) not in _VIRTUAL_MEASURE_IDS:
                    chart_fields.append(section_fields)
        filter_conditions = list(params.get('filters') or [])
        rows = get_rows_for_chart(dataset, chart_fields, filter_conditions=filter_conditions)
        return Response(rows)

@api_view(['GET'])
@permission_classes([IsAuthenticated])
def dataset_columns(request, pk: int):
    ds = get_object_or_404(
        Dataset.objects.only('id', 'owner', 'table_ref'),
        pk=pk, owner=request.user
    )

    fields = ds.fields.all()
    cols = []
    for f in fields:
        cols.append({
            "id": f.id,
            "name": f.name,
            "type": f.type,
            "aggregation": f.aggregation,
            "expression": (f.expression or "").strip(),
        })

    return Response({
        "dataset_id": pk,
        "columns": cols
    })