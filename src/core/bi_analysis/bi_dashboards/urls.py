from django.urls import path
from src.core.bi_analysis.bi_dashboards.views import (
    DashboardListCreateView,
    DashboardDetailView
)

urlpatterns = [
    path('', DashboardListCreateView.as_view(), name='dashboard-list-create'),
    path('<int:pk>/', DashboardDetailView.as_view(), name='dashboard-detail'),
]

