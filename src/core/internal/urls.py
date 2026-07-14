from django.urls import path

from src.core.internal.views import JupyterAccessView

urlpatterns = [
    path('jupyter-access/', JupyterAccessView.as_view(), name='internal-jupyter-access'),
]
