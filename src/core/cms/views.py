import logging

from rest_framework.response import Response
from rest_framework import status
from rest_framework.request import Request

from drf_yasg.utils import swagger_auto_schema
from drf_yasg import openapi

from django.contrib.auth import get_user_model

User = get_user_model()

from src.core.utils.base.base_views import BaseAPIViewAuthMixin
from src.core.cms.models import CMSPage
from src.core.settings.models import UserAvatar
from src.core.cms.scripts import normalize_cms_path, sync_cms_pages

logger = logging.getLogger(__name__)


def _has_admin_panel_access(user) -> bool:
    from src.core.cms.adp.services.permissions import PermissionService

    return PermissionService.can_access_admin_panel(user)


class CheckAccessToAdminPanel(BaseAPIViewAuthMixin):
    @swagger_auto_schema(
        operation_description="Получение прав доступа к панели администратора",
        responses={
            200: "Права доступа к панели администратора получены",
            401: "Пользователь не авторизован",
            403: "Нет доступа",
        },
    )
    def get(self, request: Request):
        from src.core.cms.adp.services.permissions import PermissionService

        is_global_admin = PermissionService.can_manage_users_as_global_admin(request.user)

        return Response(
            {
                'access_to_panel': PermissionService.can_access_admin_panel(request.user),
                'access_to_category': is_global_admin,
            },
            status=status.HTTP_200_OK,
        )


class GetUserName(BaseAPIViewAuthMixin):
    @swagger_auto_schema(
        operation_description="Получение имени текущего пользователя",
        responses={
            200: "Имя пользователя получено",
            401: "Пользователь не авторизован",
        },
    )
    def get(self, request: Request):
        return Response(request.user.username, status=status.HTTP_200_OK)


class UserPublicInfoView(BaseAPIViewAuthMixin):
    """Публичные данные пользователя (имя, аватар).

    Резолвится только по public_id (UUID, непоследовательная ссылка) — без
    числового id, чтобы исключить перебор пользователей (enumeration).
    """

    @swagger_auto_schema(
        operation_description="Получение публичных данных пользователя по public_id",
        responses={
            200: "Публичные данные пользователя",
            401: "Пользователь не авторизован",
            404: "Пользователь не найден",
        },
    )
    def get(self, request: Request, ref):
        user = User.objects.select_related('avatar').filter(public_id=ref).first()
        if user is None:
            return Response({'detail': 'Not found'}, status=status.HTTP_404_NOT_FOUND)

        avatar_url = None
        try:
            avatar = getattr(user, 'avatar', None)
            if avatar and avatar.image:
                avatar_url = avatar.image.url
        except UserAvatar.DoesNotExist:
            avatar_url = None

        first_name = (user.first_name or '').strip()
        last_name = (user.last_name or '').strip()
        middle_name = (getattr(user, 'middle_name', '') or '').strip()
        full_name = ' '.join(p for p in [last_name, first_name, middle_name] if p) or user.username

        return Response({
            'public_id': str(user.public_id) if getattr(user, 'public_id', None) else None,
            'username': user.username,
            'first_name': first_name,
            'last_name': last_name,
            'middle_name': middle_name,
            'full_name': full_name,
            'avatar_url': avatar_url,
        }, status=status.HTTP_200_OK)


class SyncAllProjectPages(BaseAPIViewAuthMixin):
    @swagger_auto_schema(
        operation_description='Синхронизация путей CMS со всеми client-маршрутами',
        responses={
            200: "Пути получены и обновлены",
            401: "Пользователь не авторизован",
            403: "Нет доступа",
            400: "Ошибка чтения маршрутов",
        },
    )
    def post(self, request: Request):
        if not _has_admin_panel_access(request.user):
            return Response(status=status.HTTP_403_FORBIDDEN)

        try:
            result = sync_cms_pages(remove_orphans=False)
            return Response(sorted(result.paths), status=status.HTTP_200_OK)
        except Exception:
            logger.exception('Ошибка синхронизации страниц CMS')
            return Response(
                {'error': 'Не удалось обновить страницы CMS.'},
                status=status.HTTP_400_BAD_REQUEST,
            )


class GetCMSPages(BaseAPIViewAuthMixin):
    @swagger_auto_schema(
        operation_description="Получение всех страниц CMS",
        responses={
            200: "Страницы получены",
            401: "Пользователь не авторизован",
            403: "Нет доступа",
        },
    )
    def get(self, request: Request):
        if not _has_admin_panel_access(request.user):
            return Response(status=status.HTTP_403_FORBIDDEN)

        from src.core.cms.client_routes_cache import get_client_routes_catalog
        from src.core.cms.models import PAGE_TYPE_WITHOUT_LIMITATIONS

        routes_catalog = get_client_routes_catalog()
        cms_pages_by_path = {
            normalize_cms_path(page.path.replace('\\\\', '\\')): page
            for page in CMSPage.objects.all()
        }

        pages_list = []
        for path in sorted(routes_catalog.keys()):
            route_meta = routes_catalog.get(path, {})
            cms_page = cms_pages_by_path.get(path)
            pages_list.append({
                'id': cms_page.id if cms_page else None,
                'path': path,
                'type': cms_page.page_type if cms_page else PAGE_TYPE_WITHOUT_LIMITATIONS,
                'module_name': route_meta.get('module_name', 'core'),
                'title': route_meta.get('title', ''),
            })

        return Response({'pages': pages_list}, status=status.HTTP_200_OK)
