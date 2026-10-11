from django.urls import include, path
from rest_framework.routers import DefaultRouter

from .views import NotificationViewSet
from .views_unsubscribe import notification_email_unsubscribe

router = DefaultRouter()
router.register(r'', NotificationViewSet, basename='notifications')

urlpatterns = [
    path(
        'email/unsubscribe/',
        notification_email_unsubscribe,
        name='notification-email-unsubscribe',
    ),
    path('', include(router.urls)),
]
