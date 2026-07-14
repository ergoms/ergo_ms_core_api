from django.urls import path

from src.core.system.views import MaintenanceStatusView, ReadyView

urlpatterns = [
    path('ready/', ReadyView.as_view(), name='system-ready'),
    path('maintenance-status/', MaintenanceStatusView.as_view(), name='maintenance-status'),
]
