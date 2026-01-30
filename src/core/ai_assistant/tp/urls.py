from rest_framework.routers import DefaultRouter
from .views import TechnologicalProcessDocumentViewSet, TPChatStreamView
from django.urls import path

router = DefaultRouter()
router.register(r'tp_documents', TechnologicalProcessDocumentViewSet, basename='tp-document')

urlpatterns = [
    path('tp_chat/stream/', TPChatStreamView.as_view(), name='ai-assistant-tp-chat-stream'),
] + router.urls
