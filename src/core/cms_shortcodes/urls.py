from django.urls import path, include
from rest_framework.routers import DefaultRouter

from .views import SiteLayoutView, SiteLayoutViewSet, TemplateViewSet, PageViewSet, InstanceViewSet, ShortcodeCategoryViewSet, PageByFullPathView

router = DefaultRouter()
router.register(r'templates', TemplateViewSet, basename='template')
router.register(r'pages', PageViewSet, basename='page')
router.register(r'instances', InstanceViewSet, basename='shortcode-instance')
router.register(r'categories', ShortcodeCategoryViewSet, basename='shortcode-category')
router.register(r'layout', SiteLayoutViewSet, basename='layout')

urlpatterns = [
    path('pages/by_path/', PageByFullPathView.as_view(), name='page-by-full-path'),
    path('layout/', SiteLayoutView.as_view(), name='site-layout'),
    path('', include(router.urls)),
]