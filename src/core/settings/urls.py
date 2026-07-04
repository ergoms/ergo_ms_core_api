from django.urls import (
    path, include
)
from rest_framework.routers import DefaultRouter
from .views import *
router = DefaultRouter()
router.register(r'security-settings', SecuritySettingsViewSet)
router.register(r'media-settings', MediaSettingsViewSet)
router.register(r'permalink-settings', PermalinkSettingsViewSet)
router.register(r'email-settings', EmailSettingsViewSet)
router.register(r'user-avatars', UserAvatarViewSet, basename='user-avatars')
router.register(r'themes', ThemeViewSet, basename='themes')

urlpatterns = [
    path('', include(router.urls)),
]
