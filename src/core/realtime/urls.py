from django.urls import path

from src.core.realtime.sync_view import RealtimeSyncView
from src.core.realtime.views import RealtimeConfigView, RealtimeStreamView, RealtimeSubscriptionView

urlpatterns = [
    path('config/', RealtimeConfigView.as_view(), name='realtime-config'),
    path('stream/', RealtimeStreamView.as_view(), name='realtime-stream'),
    path('sync/', RealtimeSyncView.as_view(), name='realtime-sync'),
    path('subscriptions/', RealtimeSubscriptionView.as_view(), name='realtime-subscriptions'),
]
