"""Базовые классы API: APIView, ViewSet, PublicIdMixin.

Модели импортируют только PublicIdMixin. Представления подгружаются
при обращении к ним, иначе разбор моделей во время django.setup
заходит в JWT и в ещё не собранный PermissionService.
"""

from src.core.utils.base.models import PublicIdMixin

__all__ = [
    'AuthenticatedAPIMixin',
    'BaseAPIView',
    'BaseAPIViewAuthMixin',
    'BaseAPIViewGlobalAdminMixin',
    'BaseAPIViewPublicMixin',
    'BaseGenericViewSet',
    'BaseModelViewSet',
    'BaseModelViewSetGlobalAdmin',
    'BaseReadOnlyModelViewSet',
    'BaseReadOnlyModelViewSetGlobalAdmin',
    'BaseViewSet',
    'BaseViewSetGlobalAdmin',
    'PUBLIC_ID_LOOKUP_REGEX',
    'PublicIdMixin',
]

_LAZY = {
    'AuthenticatedAPIMixin': ('src.core.utils.base.base_views', 'AuthenticatedAPIMixin'),
    'BaseAPIView': ('src.core.utils.base.base_views', 'BaseAPIView'),
    'BaseAPIViewAuthMixin': ('src.core.utils.base.base_views', 'BaseAPIViewAuthMixin'),
    'BaseAPIViewGlobalAdminMixin': ('src.core.utils.base.base_views', 'BaseAPIViewGlobalAdminMixin'),
    'BaseAPIViewPublicMixin': ('src.core.utils.base.base_views', 'BaseAPIViewPublicMixin'),
    'BaseGenericViewSet': ('src.core.utils.base.base_viewsets', 'BaseGenericViewSet'),
    'BaseModelViewSet': ('src.core.utils.base.base_viewsets', 'BaseModelViewSet'),
    'BaseModelViewSetGlobalAdmin': ('src.core.utils.base.base_viewsets', 'BaseModelViewSetGlobalAdmin'),
    'BaseReadOnlyModelViewSet': ('src.core.utils.base.base_viewsets', 'BaseReadOnlyModelViewSet'),
    'BaseReadOnlyModelViewSetGlobalAdmin': (
        'src.core.utils.base.base_viewsets',
        'BaseReadOnlyModelViewSetGlobalAdmin',
    ),
    'BaseViewSet': ('src.core.utils.base.base_viewsets', 'BaseViewSet'),
    'BaseViewSetGlobalAdmin': ('src.core.utils.base.base_viewsets', 'BaseViewSetGlobalAdmin'),
    'PUBLIC_ID_LOOKUP_REGEX': ('src.core.utils.base.base_viewsets', 'PUBLIC_ID_LOOKUP_REGEX'),
}


def __getattr__(name: str):
    target = _LAZY.get(name)
    if target is None:
        raise AttributeError(f'module {__name__!r} has no attribute {name!r}')
    import importlib

    module = importlib.import_module(target[0])
    value = getattr(module, target[1])
    globals()[name] = value
    return value
