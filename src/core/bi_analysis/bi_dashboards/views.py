from rest_framework import generics, permissions
from src.core.bi_analysis.bi_dashboards.models import Dashboard
from src.core.bi_analysis.bi_dashboards.serializers import (
    DashboardSerializer,
    DashboardWriteSerializer,
    DashboardShortSerializer
)
from src.core.utils.mixins import SwaggerSafeMixin


class IsDashboardOwnerOrReadOnly(permissions.BasePermission):
    """GET/HEAD/OPTIONS — любой авторизованный; PUT/PATCH/DELETE — только владелец."""

    def has_object_permission(self, request, view, obj):
        if request.method in permissions.SAFE_METHODS:
            return True
        return obj.owner_id == request.user.id


class DashboardListCreateView(SwaggerSafeMixin, generics.ListCreateAPIView):
    """
    Список и создание дашбордов.
    GET: список дашбордов пользователя
    POST: создание нового дашборда
    """
    queryset = Dashboard.objects.all()
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        if getattr(self, 'swagger_fake_view', False):
            return Dashboard.objects.none()
        return Dashboard.objects.filter(owner=self.request.user).select_related('owner')

    def get_serializer_class(self):
        if self.request and self.request.method == 'GET':
            return DashboardShortSerializer
        return DashboardWriteSerializer

    def perform_create(self, serializer):
        serializer.save(owner=self.request.user)


class DashboardDetailView(SwaggerSafeMixin, generics.RetrieveUpdateDestroyAPIView):
    """
    Детали, обновление и удаление дашборда.
    GET: любой авторизованный пользователь (просмотр в т.ч. чужого дашборда).
    PUT/PATCH/DELETE: только владелец.
    """
    queryset = Dashboard.objects.all().prefetch_related('pages__items').select_related('owner')
    permission_classes = [permissions.IsAuthenticated, IsDashboardOwnerOrReadOnly]

    def get_queryset(self):
        if getattr(self, 'swagger_fake_view', False):
            return Dashboard.objects.none()
        return Dashboard.objects.all().prefetch_related('pages__items').select_related('owner')

    def get_serializer_class(self):
        if self.request and self.request.method == 'GET':
            return DashboardSerializer
        return DashboardWriteSerializer

