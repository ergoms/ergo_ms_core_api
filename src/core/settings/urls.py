from django.urls import (
    path, include
)
from rest_framework.routers import DefaultRouter
from .views import *
router = DefaultRouter()
router.register(r'email-settings', EmailSettingsViewSet)
router.register(r'user-avatars', UserAvatarViewSet, basename='user-avatars')
router.register(r'themes', ThemeViewSet, basename='themes')

urlpatterns = [
    path('', include(router.urls)),
]
