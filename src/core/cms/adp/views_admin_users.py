"""Управление пользователями в админ-панели."""
from rest_framework.response import Response
from rest_framework import status
from rest_framework.parsers import MultiPartParser, FormParser, JSONParser
from drf_yasg.utils import swagger_auto_schema
from drf_yasg import openapi

from django.contrib.auth import get_user_model

User = get_user_model()
from django.db.models import Prefetch

from src.core.settings.models import UserAvatar
from src.core.utils.base.base_views import BaseAPIView, BaseAPIViewGlobalAdminMixin
from src.core.utils.mixins import MediaApiFileMixin
from src.core.cms.adp.services.user_search import apply_user_search
from src.core.cms.adp.models import Role, RoleGroup, UserRole, UserProfile
from src.core.cms.adp.serializers import (
    RoleSerializer,
    RoleGroupSerializer,
    AdminUserRoleInfoSerializer,
    CMSUserSerializer,
    UpdateUserProfileSerializer,
    AdminResetUserPasswordSerializer,
    AdminCreateUserSerializer,
)
from src.core.cms.adp.services.permissions import PermissionService
from src.core.cms.adp.services import presence as presence_service
from src.core.cms.adp.services.user_deletion import (
    UserDeletionBlockedError,
    delete_admin_user,
    revoke_user_auth,
)
from src.core.cms.adp.services.admin_user import AdminUserCreateError, create_admin_user
from src.config.settings.auth import IS_DEVELOPMENT
from src.core.utils.methods import (
    parse_errors_to_dict,
    generate_secure_random_password,
    send_admin_password_reset_notification,
)
from src.core.audit.shortcuts import audit_log


def _get_user_avatar_url(user):
    try:
        avatar = user.avatar
    except UserAvatar.DoesNotExist:
        avatar = None
    if avatar and avatar.image:
        return avatar.image.url
    return None


def _validate_admin_user_deletion(request, target_user):
    if request.user.id == target_user.id:
        return Response(
            {'error': 'Нельзя удалить собственную учётную запись.'},
            status=status.HTTP_400_BAD_REQUEST,
        )

    if PermissionService.can_manage_users_as_global_admin(target_user):
        if not PermissionService.can_manage_users_as_global_admin(request.user):
            return Response(
                {'error': 'Нельзя удалить глобального администратора.'},
                status=status.HTTP_400_BAD_REQUEST,
            )

    return None


def _perform_admin_user_deletion(user):
    try:
        delete_admin_user(user)
    except UserDeletionBlockedError as exc:
        payload = {
            'error': (
                'Невозможно удалить пользователя: '
                'есть связанные данные, блокирующие удаление.'
            ),
        }
        if exc.detail:
            payload['details'] = exc.detail
        return Response(payload, status=status.HTTP_400_BAD_REQUEST)

    return None


def _apply_system_password_reset(user):
    generated_password = generate_secure_random_password()
    try:
        user.set_password(generated_password)
        user.save(update_fields=['password'])
    finally:
        del generated_password


def _is_manual_password_reset_request(request):
    if not IS_DEVELOPMENT:
        return False
    new_password = (request.data.get('new_password') or '').strip()
    confirm_password = (request.data.get('confirm_password') or '').strip()
    return bool(new_password and confirm_password)


def _build_admin_user_full_name(user):
    if hasattr(user, 'get_full_name'):
        return user.get_full_name() or user.username
    name_parts = [user.first_name]
    middle_name = getattr(user, 'middle_name', None)
    if middle_name:
        name_parts.append(middle_name)
    if user.last_name:
        name_parts.append(user.last_name)
    return " ".join(part for part in name_parts if part and str(part).strip()) or user.username


def _get_active_user_role_from_prefetch(user):
    active_roles = getattr(user, '_active_roles', None)
    return active_roles[0] if active_roles else None


def _get_admin_user_role_for_display(user):
    user_role = (
        UserRole.objects
        .filter(user=user, is_active=True)
        .select_related('role')
        .prefetch_related('role_groups')
        .first()
    )
    if user_role or PermissionService.is_admin(user):
        return user_role

    return PermissionService.get_user_role(user)


def _build_admin_user_list_item(user, user_role=None, admin_role=None, presence_entry=None):
    if user_role is None:
        user_role = _get_active_user_role_from_prefetch(user)

    role = PermissionService.resolve_display_role(
        user,
        user_role,
        admin_role=admin_role,
    )
    role_groups = list(user_role.role_groups.all()) if user_role else []

    if presence_entry is None:
        presence_entry = presence_service.PresenceEntry(is_online=False, last_seen=None)

    return {
        'user_id': user.id,
        'public_id': str(user.public_id) if getattr(user, 'public_id', None) else None,
        'username': user.username,
        'email': user.email or '',
        'full_name': _build_admin_user_full_name(user),
        'first_name': user.first_name or '',
        'last_name': user.last_name or '',
        'date_joined': user.date_joined,
        'last_login': user.last_login,
        'is_online': presence_entry.is_online,
        'last_seen': presence_entry.last_seen,
        'role': role,
        'role_groups': role_groups,
        'avatar_url': _get_user_avatar_url(user),
    }


def _parse_admin_users_pagination(request):
    try:
        page = max(1, int(request.query_params.get('page', 1)))
    except (TypeError, ValueError):
        page = 1

    try:
        page_size = min(100, max(1, int(request.query_params.get('page_size', 12))))
    except (TypeError, ValueError):
        page_size = 12

    search = (request.query_params.get('search') or '').strip()
    return page, page_size, search


def _parse_online_only_param(request) -> bool:
    raw = (request.query_params.get('online_only') or '').strip().lower()
    return raw in ('true', '1', 'yes')


def _get_admin_users_queryset(search='', online_only=False):
    active_roles_qs = (
        UserRole.objects
        .filter(is_active=True)
        .select_related('role')
        .prefetch_related('role_groups')
    )

    users_qs = (
        User.objects
        .select_related('avatar')
        .prefetch_related(
            Prefetch('user_roles', queryset=active_roles_qs, to_attr='_active_roles')
        )
        .order_by('last_name', 'first_name', 'username')
    )

    if online_only:
        cutoff = presence_service.get_presence_stale_cutoff()
        users_qs = users_qs.filter(
            presence__connection_count__gt=0,
            presence__last_seen__gte=cutoff,
        )

    return apply_user_search(users_qs, search)


def _build_admin_user_detail(user):
    admin_role = PermissionService._get_or_create_admin_role()
    user_role = _get_admin_user_role_for_display(user)
    role = PermissionService.resolve_display_role(
        user,
        user_role,
        admin_role=admin_role,
    )
    role_groups = list(user_role.role_groups.all()) if user_role else []

    data = CMSUserSerializer(user).data
    data['user_id'] = user.id
    data['public_id'] = str(user.public_id) if getattr(user, 'public_id', None) else None
    data['role'] = RoleSerializer(role).data if role else None
    data['role_groups'] = RoleGroupSerializer(role_groups, many=True).data
    data['avatar_url'] = _get_user_avatar_url(user)
    data['password_reset_mode'] = 'manual' if IS_DEVELOPMENT else 'system'
    return data


class AdminUserRoleListView(BaseAPIViewGlobalAdminMixin, BaseAPIView):
    """
    Получение списка пользователей и их ролей для администраторов.
    """
    
    @swagger_auto_schema(
        operation_description=(
            "Получить список пользователей и их ролей. "
            "Поддерживает пагинацию (page, page_size) и поиск (search)."
        ),
        manual_parameters=[
            openapi.Parameter(
                'page',
                openapi.IN_QUERY,
                description='Номер страницы (по умолчанию 1)',
                type=openapi.TYPE_INTEGER,
                required=False,
            ),
            openapi.Parameter(
                'page_size',
                openapi.IN_QUERY,
                description='Размер страницы (по умолчанию 12, максимум 100)',
                type=openapi.TYPE_INTEGER,
                required=False,
            ),
            openapi.Parameter(
                'search',
                openapi.IN_QUERY,
                description='Поиск по словам (через пробел) по username, email, имени, фамилии и отчеству',
                type=openapi.TYPE_STRING,
                required=False,
            ),
            openapi.Parameter(
                'online_only',
                openapi.IN_QUERY,
                description='Только пользователи с активным WS-подключением (true, 1, yes)',
                type=openapi.TYPE_BOOLEAN,
                required=False,
            ),
        ],
        responses={200: AdminUserRoleInfoSerializer(many=True)}
    )
    def get(self, request):
        page, page_size, search = _parse_admin_users_pagination(request)
        online_only = _parse_online_only_param(request)
        users_qs = _get_admin_users_queryset(search, online_only=online_only)
        total = users_qs.count()
        offset = (page - 1) * page_size
        users = list(users_qs[offset:offset + page_size])
        admin_role = PermissionService._get_or_create_admin_role()
        presence_map = presence_service.get_presence_map([user.id for user in users])

        items = [
            _build_admin_user_list_item(
                user,
                admin_role=admin_role,
                presence_entry=presence_map.get(user.id),
            )
            for user in users
        ]
        serializer = AdminUserRoleInfoSerializer(items, many=True)

        return Response({
            'users': serializer.data,
            'total': total,
            'page': page,
            'page_size': page_size,
        })

    @swagger_auto_schema(
        operation_description=(
            "Создать пользователя вручную (без приглашения и независимо от режима регистрации)."
        ),
        request_body=AdminCreateUserSerializer,
        responses={201: CMSUserSerializer(), 400: 'Ошибка валидации данных.'},
    )
    def post(self, request):
        serializer = AdminCreateUserSerializer(data=request.data)
        if not serializer.is_valid():
            errors = parse_errors_to_dict(serializer.errors)
            return Response(errors, status=status.HTTP_400_BAD_REQUEST)

        data = serializer.validated_data
        try:
            user, meta = create_admin_user(
                username=data['username'],
                created_by=request.user,
                password=data.get('password') or '',
                first_name=data.get('first_name') or '',
                last_name=data.get('last_name') or '',
                middle_name=data.get('middle_name') or '',
                email=data.get('email') or '',
                role_id=data.get('role_id'),
                role_group_ids=data.get('role_group_ids') or [],
                send_password_notification=data.get('send_password_notification', True),
            )
        except AdminUserCreateError as exc:
            return Response({'error': exc.message}, status=status.HTTP_400_BAD_REQUEST)

        user = User.objects.select_related('adp_profile').get(pk=user.pk)
        audit_log('user.created', request=request, severity='security',
               entity={'type': 'user', 'label': user.get_full_name() or user.username},
               meta={'username': user.username})
        response_data = _build_admin_user_detail(user)
        response_data.update(meta)
        return Response(response_data, status=status.HTTP_201_CREATED)


class AdminUserDetailView(BaseAPIViewGlobalAdminMixin, BaseAPIView):
    """
    Получение и обновление профиля пользователя администратором.
    """

    def _get_target_user(self, user_id):
        try:
            return User.objects.select_related('adp_profile').get(pk=user_id)
        except User.DoesNotExist:
            return None

    @swagger_auto_schema(
        operation_description="Получить полный профиль пользователя (для админ-панели)",
        responses={200: CMSUserSerializer()},
    )
    def get(self, request, user_id):
        user = self._get_target_user(user_id)
        if not user:
            return Response(
                {'error': 'Пользователь не найден'},
                status=status.HTTP_404_NOT_FOUND,
            )

        UserProfile.objects.get_or_create(user=user)
        return Response(_build_admin_user_detail(user), status=status.HTTP_200_OK)

    @swagger_auto_schema(
        operation_description="Обновить профиль пользователя (для админ-панели)",
        request_body=UpdateUserProfileSerializer,
        responses={200: CMSUserSerializer(), 400: 'Ошибка валидации данных.'},
    )
    def put(self, request, user_id):
        user = self._get_target_user(user_id)
        if not user:
            return Response(
                {'error': 'Пользователь не найден'},
                status=status.HTTP_404_NOT_FOUND,
            )

        profile, _ = UserProfile.objects.get_or_create(user=user)
        serializer = UpdateUserProfileSerializer(profile, data=request.data, partial=True)

        if serializer.is_valid():
            serializer.save()
            user = User.objects.select_related('adp_profile').get(pk=user_id)
            audit_log('user.updated', request=request,
                   entity={'type': 'user', 'label': user.get_full_name() or user.username},
                   meta={'username': user.username})
            return Response(_build_admin_user_detail(user), status=status.HTTP_200_OK)

        errors = parse_errors_to_dict(serializer.errors)
        return Response(errors, status=status.HTTP_400_BAD_REQUEST)

    @swagger_auto_schema(
        operation_description="Удалить пользователя (для админ-панели)",
        responses={
            204: 'Пользователь удалён',
            400: 'Нельзя удалить пользователя',
            404: 'Пользователь не найден',
        },
    )
    def delete(self, request, user_id):
        user = self._get_target_user(user_id)
        if not user:
            return Response(
                {'error': 'Пользователь не найден'},
                status=status.HTTP_404_NOT_FOUND,
            )

        validation_error = _validate_admin_user_deletion(request, user)
        if validation_error:
            return validation_error

        target_label = user.get_full_name() or user.username
        target_username = user.username
        deletion_error = _perform_admin_user_deletion(user)
        if deletion_error:
            return deletion_error

        audit_log('user.deleted', request=request, severity='security',
               entity={'type': 'user', 'label': target_label},
               meta={'username': target_username})
        return Response(status=status.HTTP_204_NO_CONTENT)


class AdminUserAvatarView(MediaApiFileMixin, BaseAPIViewGlobalAdminMixin, BaseAPIView):
    """
    Загрузка и удаление аватара пользователя администратором.
    """
    parser_classes = [JSONParser, MultiPartParser, FormParser]

    def _get_target_user(self, user_id):
        try:
            return User.objects.get(pk=user_id)
        except User.DoesNotExist:
            return None

    @swagger_auto_schema(
        operation_description="Загрузить или заменить аватар пользователя (для админ-панели)",
        responses={200: 'Аватар обновлён', 404: 'Пользователь не найден'},
    )
    def post(self, request, user_id):
        user = self._get_target_user(user_id)
        if not user:
            return Response(
                {'error': 'Пользователь не найден'},
                status=status.HTTP_404_NOT_FOUND,
            )

        file, file_path = self.get_file_or_path('image')
        if not file and not file_path:
            return Response(
                {'error': 'Файл изображения не передан'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        UserAvatar.objects.filter(user=user).delete()
        avatar = UserAvatar.objects.create(user=user)
        if file:
            avatar.image.save(file.name, file, save=False)
        elif file_path:
            self.assign_file_field(avatar, 'image', file_path=file_path)
        avatar.save()

        return Response(
            {'avatar_url': _get_user_avatar_url(user)},
            status=status.HTTP_200_OK,
        )

    @swagger_auto_schema(
        operation_description="Удалить аватар пользователя (для админ-панели)",
        responses={204: 'Аватар удалён', 404: 'Пользователь или аватар не найден'},
    )
    def delete(self, request, user_id):
        user = self._get_target_user(user_id)
        if not user:
            return Response(
                {'error': 'Пользователь не найден'},
                status=status.HTTP_404_NOT_FOUND,
            )

        avatar = UserAvatar.objects.filter(user=user).first()
        if avatar:
            avatar.delete()
            return Response(status=status.HTTP_204_NO_CONTENT)

        return Response(
            {'detail': 'Аватар не найден'},
            status=status.HTTP_404_NOT_FOUND,
        )


class AdminUserResetPasswordView(BaseAPIViewGlobalAdminMixin, BaseAPIView):
    """
    Сброс пароля пользователя администратором.
    Production: случайный пароль + уведомление на email.
    Development: ручная установка пароля при передаче new_password и confirm_password.
    """

    def _get_target_user(self, user_id):
        try:
            return User.objects.get(pk=user_id)
        except User.DoesNotExist:
            return None

    @swagger_auto_schema(
        operation_description="Сбросить пароль пользователя (админ-панель)",
        request_body=AdminResetUserPasswordSerializer,
        responses={200: 'Пароль сброшен или установлен'},
    )
    def post(self, request, user_id):
        if request.user.id == user_id:
            return Response(
                {'error': 'Нельзя сбросить пароль собственной учётной записи через эту форму.'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        user = self._get_target_user(user_id)
        if not user:
            return Response(
                {'error': 'Пользователь не найден'},
                status=status.HTTP_404_NOT_FOUND,
            )

        if _is_manual_password_reset_request(request):
            serializer = AdminResetUserPasswordSerializer(data=request.data)
            if not serializer.is_valid():
                errors = parse_errors_to_dict(serializer.errors)
                return Response(errors, status=status.HTTP_400_BAD_REQUEST)

            user.set_password(serializer.validated_data['new_password'])
            user.save(update_fields=['password'])
            revoke_user_auth(user)

            audit_log('user.password_reset_by_admin', request=request, severity='security',
                   entity={'type': 'user', 'label': user.get_full_name() or user.username},
                   meta={'username': user.username, 'mode': 'manual'})
            return Response(
                {
                    'message': 'Пароль установлен.',
                    'mode': 'manual',
                },
                status=status.HTTP_200_OK,
            )

        email = (user.email or '').strip()

        _apply_system_password_reset(user)
        revoke_user_auth(user)

        audit_log('user.password_reset_by_admin', request=request, severity='security',
               entity={'type': 'user', 'label': user.get_full_name() or user.username},
               meta={'username': user.username, 'mode': 'system'})

        email_sent = False
        email_error = None
        if email:
            email_sent, email_error = send_admin_password_reset_notification(email)
        else:
            email_error = 'У пользователя не указан email — уведомление не отправлено.'

        response_data = {
            'message': 'Пароль сброшен.',
            'mode': 'system',
            'email_sent': email_sent,
        }
        if email_sent:
            response_data['message'] = 'Пароль сброшен. Пользователю отправлено уведомление.'
        else:
            response_data['warning'] = (
                email_error or 'Не удалось отправить уведомление на email пользователя.'
            )

        return Response(response_data, status=status.HTTP_200_OK)
