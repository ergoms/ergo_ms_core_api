from django.urls import path

from src.core.bi_analysis.bi_connections.views import ConnectionListCreateView, ConnectionDetailView, CheckConnectionView, ConnectionTablesView, ConnectionFilesStatusView

urlpatterns = [
    path('', ConnectionListCreateView.as_view(), name='connection-list-create'),
    path('<int:pk>/', ConnectionDetailView.as_view(), name='connection-detail'),
    path("check-connection/", CheckConnectionView.as_view(), name="check-connection"),
    path('<int:connection_id>/tables/', ConnectionTablesView.as_view(), name='connection-tables'),
    path('files-status/', ConnectionFilesStatusView.as_view(), name='connection-files-status'),
]