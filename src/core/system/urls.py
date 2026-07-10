from django.urls import path

from src.core.system.views import MaintenanceStatusView

urlpatterns = [
    path('maintenance-status/', MaintenanceStatusView.as_view(), name='maintenance-status'),
]
