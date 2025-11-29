from django.urls import path, include

urlpatterns = [
    path('bi_datasets/', include('src.core.bi_analysis.bi_datasets.urls')),
    path('bi_connections/', include('src.core.bi_analysis.bi_connections.urls')),
    path('bi_charts/', include('src.core.bi_analysis.bi_charts.urls')),
    path('bi_dashboards/', include('src.core.bi_analysis.bi_dashboards.urls')),
]