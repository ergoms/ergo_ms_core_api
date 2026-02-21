from django.urls import path, re_path
from rest_framework.routers import DefaultRouter
from .views import (
    UserFilesListView, BIQueryView, OllamaStatusView, ChartAnalysisView,
    ChatView, ChatStreamView, ChatSessionViewSet, KnowledgeDocumentViewSet,
    EmbeddingsStatusView, GeneratedDocumentDownloadView,
)

router = DefaultRouter()
router.register(r'chat_sessions', ChatSessionViewSet, basename='chat-session')
router.register(r'knowledge_documents', KnowledgeDocumentViewSet, basename='knowledge-document')

urlpatterns = [
    path('files/', UserFilesListView.as_view(), name='ai-assistant-files'),
    path('bi_query/', BIQueryView.as_view(), name='ai-assistant-bi-query'),
    path('ollama_status/', OllamaStatusView.as_view(), name='ai-assistant-ollama-status'),
    path('embeddings_status/', EmbeddingsStatusView.as_view(), name='ai-assistant-embeddings-status'),
    path('chart_analysis/', ChartAnalysisView.as_view(), name='ai-assistant-chart-analysis'),
    path('chat/', ChatView.as_view(), name='ai-assistant-chat'),
    path('chat/stream/', ChatStreamView.as_view(), name='ai-assistant-chat-stream'),
    re_path(r'^documents/download/(?P<file_path>.+)$', GeneratedDocumentDownloadView.as_view(), name='ai-assistant-document-download'),
] + router.urls
