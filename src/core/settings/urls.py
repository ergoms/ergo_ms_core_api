from django.urls import (
    path, include
)
from rest_framework.routers import DefaultRouter
from .views import *
router = DefaultRouter()
router.register(r'general-settings', GeneralSettingsViewSet)
router.register(r'appearance-settings', AppearanceSettingsViewSet)
router.register(r'security-settings', SecuritySettingsViewSet)
router.register(r'media-settings', MediaSettingsViewSet)
router.register(r'permalink-settings', PermalinkSettingsViewSet)
router.register(r'email-settings', EmailSettingsViewSet)
router.register(r'file', FileViewSet)
router.register(r'categories', CategoryViewSet)
router.register(r'tags', TagViewSet)
router.register('audit-logs', AuditLogViewSet, basename='auditlog')
router.register(r'user-avatars', UserAvatarViewSet, basename='user-avatars')
router.register(r'themes', ThemeViewSet, basename='themes')

urlpatterns = [
    path('files/<str:filename>', FileDownloadByNameView.as_view(), name='file-download-by-name'),
    path('', include(router.urls)),
]
