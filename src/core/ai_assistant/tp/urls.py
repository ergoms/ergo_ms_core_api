from django.urls import path
from rest_framework.routers import DefaultRouter

from .views import (
    TechnologicalProcessDocumentViewSet,
    TPChatStreamView,
    TPUploadStatusView,
    TPChatStatusView,
)

router = DefaultRouter()
router.register(r'tp_documents', TechnologicalProcessDocumentViewSet, basename='tp-document')

urlpatterns = [
    path('tp_chat/stream/', TPChatStreamView.as_view(), name='ai-assistant-tp-chat-stream'),
    path(
        'tp_chat/status/<str:task_id>/',
        TPChatStatusView.as_view(),
        name='ai-assistant-tp-chat-status',
    ),
    path(
        'tp_documents/upload_status/<str:task_id>/',
        TPUploadStatusView.as_view(),
        name='ai-assistant-tp-upload-status',
    ),
] + router.urls
