"""
Файл содержащий маршруты (URL-patterns) для Django-приложения.
"""

from django.urls import path

from src.core.utils.media_views import MediaUploadTokenView

urlpatterns = [
    path('media/upload-token/', MediaUploadTokenView.as_view(), name='media-upload-token'),
]