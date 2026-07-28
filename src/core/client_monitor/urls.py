from django.urls import include, path
from rest_framework.routers import DefaultRouter

from .views import ClientMonitorSessionViewSet

router = DefaultRouter()
router.register(r'sessions', ClientMonitorSessionViewSet, basename='client-monitor-sessions')

urlpatterns = [
    path('', include(router.urls)),
]

