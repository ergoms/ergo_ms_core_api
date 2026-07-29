"""URL внутреннего ModuleBridge API."""

from django.urls import path

from . import internal_views

urlpatterns = [
    path('bridge/call', internal_views.bridge_call, name='internal_bridge_call'),
    path('bridge/has', internal_views.bridge_has, name='internal_bridge_has'),
    path('bridge/all', internal_views.bridge_all, name='internal_bridge_all'),
]
