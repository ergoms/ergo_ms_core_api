from django.urls import path
from .views import UserFilesListView, BIQueryView, OllamaStatusView

urlpatterns = [
    path('files/', UserFilesListView.as_view(), name='ai-assistant-files'),
    path('bi_query/', BIQueryView.as_view(), name='ai-assistant-bi-query'),
    path('ollama_status/', OllamaStatusView.as_view(), name='ai-assistant-ollama-status'),
]




