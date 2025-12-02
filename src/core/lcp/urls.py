from django.urls import path, include
from rest_framework.routers import DefaultRouter

from .views import (
    LcpModuleViewSet, LcpPageViewSet,
    LcpComponentCategoryViewSet, LcpComponentTemplateViewSet,
    LcpDataSourceViewSet, LcpDatabaseTableViewSet,
    LcpActionViewSet, LcpVariableViewSet, LcpAuditLogViewSet
)

router = DefaultRouter()
router.register(r'modules', LcpModuleViewSet, basename='lcp-modules')
router.register(r'pages', LcpPageViewSet, basename='lcp-pages')
router.register(r'component-categories', LcpComponentCategoryViewSet, basename='lcp-component-categories')
router.register(r'component-templates', LcpComponentTemplateViewSet, basename='lcp-component-templates')
router.register(r'data-sources', LcpDataSourceViewSet, basename='lcp-data-sources')
router.register(r'database-tables', LcpDatabaseTableViewSet, basename='lcp-database-tables')
router.register(r'actions', LcpActionViewSet, basename='lcp-actions')
router.register(r'variables', LcpVariableViewSet, basename='lcp-variables')
router.register(r'audit', LcpAuditLogViewSet, basename='lcp-audit')

urlpatterns = [
    path('', include(router.urls)),
]


