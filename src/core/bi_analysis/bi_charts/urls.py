from django.urls import path
from src.core.bi_analysis.bi_charts.views import ChartListCreateView, ChartDetailView, ChartRowsAPIView
from src.core.bi_analysis.bi_charts.views import dataset_columns

urlpatterns = [
    path('', ChartListCreateView.as_view(), name='chart-list-create'),
    path('<int:pk>/', ChartDetailView.as_view(), name='chart-detail'),
    path('<int:pk>/columns/', dataset_columns, name='bi_charts-dataset-columns'),
    path('<int:pk>/rows/', ChartRowsAPIView.as_view()),
]