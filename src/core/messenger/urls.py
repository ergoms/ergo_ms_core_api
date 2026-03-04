from django.urls import include, path
from rest_framework.routers import DefaultRouter

from .views import MessageAttachmentViewSet, MessageViewSet

router = DefaultRouter()
router.register(r'messages', MessageViewSet, basename='messenger-messages')
router.register(r'attachments', MessageAttachmentViewSet, basename='messenger-attachments')

urlpatterns = [
    path('', include(router.urls)),
]
