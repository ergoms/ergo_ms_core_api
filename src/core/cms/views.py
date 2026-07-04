import re

from rest_framework.response import Response
from rest_framework import status
from rest_framework.request import Request

from drf_yasg.utils import swagger_auto_schema
from drf_yasg import openapi

from django.contrib.auth.models import User

from src.core.utils.base.base_views import BaseAPIViewAuthMixin
from src.core.cms.models import Accession, CMSPage, CMSPageComponent
from src.core.settings.models import UserAvatar
from src.core.cms.commands import GetUserExpandedPermissions
from src.core.utils.auto_api.auto_config import ModuleDiscoverer


def _normalize_path(path: str) -> str:
    if not path:
        return path
    if path == '/':
        return '/'
    return path[:-1] if path.endswith('/') else path


def _discover_client_routes_index() -> dict[str, str]:
    path_to_module: dict[str, str] = {}

    discoverer = ModuleDiscoverer()
    route_modules = discoverer.discover_client_route_modules()

    for module_key, routes_path in route_modules.items():
        try:
            _, module_name = module_key.split(':', 1)
        except ValueError:
            module_name = module_key

        try:
            with open(routes_path, 'r', encoding='utf-8') as routes_file:
                routes_content = routes_file.read()

            module_paths = re.findall(
                r'["\']path["\']\s*:\s*["\'](.*?)["\']',
                routes_content,
            )

            for route_path in module_paths:
                cleaned_path = route_path.replace('\\\\', '\\')
                normalized = _normalize_path(cleaned_path)
                path_to_module.setdefault(normalized, module_name)
        except Exception:
            continue

    return path_to_module


def _has_legacy_admin_mark(user) -> bool:
    for exp in GetUserExpandedPermissions(user):
        if exp.permission_mark.id == 4:
            return True
    return False


def _has_admin_panel_access(user) -> bool:
    from src.core.cms.adp.services.permissions import PermissionService

    if PermissionService.can_manage_users_as_global_admin(user):
        return True
    return _has_legacy_admin_mark(user)


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
        has_legacy_access = _has_legacy_admin_mark(request.user)

        return Response(
            {
                'access_to_panel': is_global_admin or has_legacy_access,
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
            'user_id': user.id,
            'public_id': str(user.public_id) if getattr(user, 'public_id', None) else None,
            'username': user.username,
            'first_name': first_name,
            'last_name': last_name,
            'middle_name': middle_name,
            'full_name': full_name,
            'avatar_url': avatar_url,
        }, status=status.HTTP_200_OK)


class PatchAllProgectPages(BaseAPIViewAuthMixin):
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
            client_routes_index = _discover_client_routes_index()
            normalized_paths = set(client_routes_index.keys())

            for path in normalized_paths:
                normalized = _normalize_path(path)
                candidates = CMSPage.objects.filter(path__in=[normalized, f'{normalized}/'])
                if candidates.exists():
                    main_page = candidates.first()
                    if main_page.path != normalized:
                        main_page.path = normalized
                        main_page.save(update_fields=['path'])
                    candidates.exclude(pk=main_page.pk).delete()
                else:
                    CMSPage.objects.create(path=normalized)

            return Response(sorted(normalized_paths), status=status.HTTP_200_OK)
        except Exception as e:
            return Response({'error': str(e)}, status=status.HTTP_400_BAD_REQUEST)


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

        path_to_module = _discover_client_routes_index()
        pages_list = []
        for page in CMSPage.objects.all():
            raw_path = page.path.replace('\\\\', '\\')
            normalized_path = _normalize_path(raw_path)
            module_name = path_to_module.get(normalized_path, 'core')
            pages_list.append({
                'id': page.id,
                'path': page.path,
                'type': page.liminationtype,
                'module_name': module_name,
            })

        return Response({'pages': pages_list}, status=status.HTTP_200_OK)


class UpdatePageLiminationType(BaseAPIViewAuthMixin):
    @swagger_auto_schema(
        operation_description="Обновление типа доступа страницы CMS",
        responses={
            200: "Страница обновлена",
            401: "Пользователь не авторизован",
            403: "Нет доступа",
            400: "Неверные данные",
        },
        request_body=openapi.Schema(
            type=openapi.TYPE_OBJECT,
            properties={
                'path': openapi.Schema(type=openapi.TYPE_STRING, description='Путь страницы'),
                'limination_type': openapi.Schema(type=openapi.TYPE_STRING, description='Тип доступа'),
            },
        ),
    )
    def put(self, request: Request):
        if not _has_admin_panel_access(request.user):
            return Response(status=status.HTTP_403_FORBIDDEN)

        try:
            page = CMSPage.objects.get(path=request.data['path'])
            page.liminationtype = request.data['limination_type']
            page.save()
            return Response(status=status.HTTP_200_OK)
        except CMSPage.DoesNotExist:
            return Response(status=status.HTTP_400_BAD_REQUEST)


class AddPageComponent(BaseAPIViewAuthMixin):
    @swagger_auto_schema(
        operation_description="Добавление компонента к странице",
        responses={
            200: "Компонент добавлен",
            401: "Пользователь не авторизован",
            403: "Нет доступа",
            400: "Неверные данные",
        },
        request_body=openapi.Schema(
            type=openapi.TYPE_OBJECT,
            properties={
                'path': openapi.Schema(type=openapi.TYPE_STRING, description='Путь страницы'),
                'component_id': openapi.Schema(type=openapi.TYPE_STRING, description='ID компонента'),
            },
        ),
    )
    def post(self, request: Request):
        if not _has_admin_panel_access(request.user):
            return Response(status=status.HTTP_403_FORBIDDEN)

        try:
            page = CMSPage.objects.get(path=request.data['path'])
            existing_components = CMSPageComponent.objects.filter(
                page=page,
                componentid=request.data['component_id'],
            )
            if existing_components.exists():
                return Response(
                    {'error': 'Такой компонент уже существует на странице'},
                    status=status.HTTP_400_BAD_REQUEST,
                )

            CMSPageComponent.objects.create(
                page=page,
                componentid=request.data['component_id'],
            )
            return Response({'message': 'Компонент успешно добавлен'}, status=status.HTTP_200_OK)
        except CMSPage.DoesNotExist:
            return Response({'error': 'Страница не найдена'}, status=status.HTTP_400_BAD_REQUEST)


class RemovePageComponent(BaseAPIViewAuthMixin):
    @swagger_auto_schema(
        operation_description="Удаление компонента со страницы",
        responses={
            200: "Компонент удален",
            401: "Пользователь не авторизован",
            403: "Нет доступа",
            400: "Неверные данные",
        },
        manual_parameters=[
            openapi.Parameter('path', openapi.IN_QUERY, description="Путь страницы", type=openapi.TYPE_STRING),
            openapi.Parameter('component_id', openapi.IN_QUERY, description="ID компонента", type=openapi.TYPE_STRING),
        ],
    )
    def delete(self, request: Request):
        if not _has_admin_panel_access(request.user):
            return Response(status=status.HTTP_403_FORBIDDEN)

        try:
            page = CMSPage.objects.get(path=request.query_params.get('path'))
            component = CMSPageComponent.objects.get(
                page=page,
                componentid=request.query_params.get('component_id'),
            )
            if Accession.objects.filter(component_id=component).exists():
                return Response(
                    {'message': 'Нельзя удалить компонент, пока он связан с правами'},
                    status=status.HTTP_200_OK,
                )

            component.delete()
            return Response({'message': 'Компонент успешно удален'}, status=status.HTTP_200_OK)
        except CMSPageComponent.DoesNotExist:
            return Response({'error': 'Компонент не найден на странице'}, status=status.HTTP_400_BAD_REQUEST)
        except CMSPage.DoesNotExist:
            return Response({'error': 'Страница не найдена'}, status=status.HTTP_400_BAD_REQUEST)


class UpdatePageComponent(BaseAPIViewAuthMixin):
    @swagger_auto_schema(
        operation_description="Изменение ID компонента на странице",
        responses={
            200: "Компонент обновлен",
            401: "Пользователь не авторизован",
            403: "Нет доступа",
            400: "Неверные данные",
        },
        request_body=openapi.Schema(
            type=openapi.TYPE_OBJECT,
            properties={
                'path': openapi.Schema(type=openapi.TYPE_STRING, description='Путь страницы'),
                'old_component_id': openapi.Schema(type=openapi.TYPE_STRING, description='Старый ID'),
                'new_component_id': openapi.Schema(type=openapi.TYPE_STRING, description='Новый ID'),
            },
        ),
    )
    def put(self, request: Request):
        if not _has_admin_panel_access(request.user):
            return Response(status=status.HTTP_403_FORBIDDEN)

        try:
            page = CMSPage.objects.get(path=request.data['path'])
            component = CMSPageComponent.objects.get(
                page=page,
                componentid=request.data['old_component_id'],
            )
            if CMSPageComponent.objects.filter(
                page=page,
                componentid=request.data['new_component_id'],
            ).exists():
                return Response(
                    {'error': 'Компонент с таким ID уже существует на странице'},
                    status=status.HTTP_400_BAD_REQUEST,
                )

            component.componentid = request.data['new_component_id']
            component.save()
            return Response({'message': 'ID компонента успешно обновлен'}, status=status.HTTP_200_OK)
        except CMSPageComponent.DoesNotExist:
            return Response({'error': 'Компонент не найден на странице'}, status=status.HTTP_400_BAD_REQUEST)


class GetPageComponents(BaseAPIViewAuthMixin):
    @swagger_auto_schema(
        operation_description="Получение всех компонентов страниц",
        responses={
            200: "Компоненты получены",
            401: "Пользователь не авторизован",
            403: "Нет доступа",
        },
    )
    def get(self, request: Request):
        if not _has_admin_panel_access(request.user):
            return Response(status=status.HTTP_403_FORBIDDEN)

        components_list = [
            {'id': component.componentid, 'page_path': component.page.path}
            for component in CMSPageComponent.objects.all()
        ]
        return Response({'components': components_list}, status=status.HTTP_200_OK)
