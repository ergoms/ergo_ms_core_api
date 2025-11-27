from django.urls import path
from .views import UserFilesListView, BIQueryView, OllamaStatusView, ChartAnalysisView, ChatView, ChatStreamView

urlpatterns = [
    path('files/', UserFilesListView.as_view(), name='ai-assistant-files'),
    path('bi_query/', BIQueryView.as_view(), name='ai-assistant-bi-query'),
    path('ollama_status/', OllamaStatusView.as_view(), name='ai-assistant-ollama-status'),
    path('chart_analysis/', ChartAnalysisView.as_view(), name='ai-assistant-chart-analysis'),
    path('chat/', ChatView.as_view(), name='ai-assistant-chat'),
    path('chat/stream/', ChatStreamView.as_view(), name='ai-assistant-chat-stream'),
]
