"""Управление пользователями в админ-панели."""
import logging

from rest_framework.response import Response
from rest_framework import status
from rest_framework.parsers import MultiPartParser, FormParser, JSONParser
from drf_yasg.utils import swagger_auto_schema
from drf_yasg import openapi

from django.contrib.auth import get_user_model
from django.utils.translation import gettext as _

User = get_user_model()
from django.db.models import Prefetch

from src.core.settings.models import UserAvatar
from src.core.utils.base.base_views import BaseAPIView, BaseAPIViewGlobalAdminMixin
from src.core.utils.mixins import MediaApiFileMixin
from src.core.cms.adp.services.user_search import apply_user_search
from src.core.cms.adp.models import Role, RoleGroup, UserRole, UserProfile, UserDevice
from src.core.cms.adp.serializers import (
    RoleSerializer,
    RoleGroupSerializer,
    AdminUserRoleInfoSerializer,
    CMSUserSerializer,
    UpdateUserProfileSerializer,
    AdminResetUserPasswordSerializer,
    AdminCreateUserSerializer,
    UserDeviceSerializer,
)
from src.core.cms.adp.services.session_devices import (
    is_current_device,
    revoke_user_device_session,
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

logger = logging.getLogger(__name__)


class _AdminUserTargetMixin:
    """Resolve admin target user by public_id."""

    def _resolve_target_user(self, request, *, ref=None, select_related=True):
        if ref is None:
            return None

        qs = User.objects.filter(public_id=ref)
        if select_related:
            qs = qs.select_related('adp_profile')
        return qs.first()


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
            {'error': _('Нельзя удалить собственную учётную запись.')},
            status=status.HTTP_400_BAD_REQUEST,
        )

    if PermissionService.can_manage_users_as_global_admin(target_user):
        if not PermissionService.can_manage_users_as_global_admin(request.user):
            return Response(
                {'error': _('Нельзя удалить глобального администратора.')},
                status=status.HTTP_400_BAD_REQUEST,
            )

    return None


def _validate_admin_user_suspend(request, target_user):
    if request.user.id == target_user.id:
        return Response(
            {'error': _('Нельзя приостановить собственную учётную запись.')},
            status=status.HTTP_400_BAD_REQUEST,
        )

    if PermissionService.is_admin(target_user) and PermissionService.count_global_admins() <= 1:
        return Response(
            {'error': _('Нельзя приостановить последнего администратора системы.')},
            status=status.HTTP_400_BAD_REQUEST,
        )

    return None


def _set_admin_user_active(user, *, is_active: bool) -> None:
    if user.is_active == is_active:
        return
    user.is_active = is_active
    user.save(update_fields=['is_active'])
    if not is_active:
        revoke_user_auth(user)


def _perform_admin_user_deletion(user):
    try:
        delete_admin_user(user)
    except UserDeletionBlockedError as exc:
        payload = {
            'error': _(
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
        'is_active': bool(user.is_active),
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


class AdminUserDetailView(_AdminUserTargetMixin, BaseAPIViewGlobalAdminMixin, BaseAPIView):
    """
    Получение и обновление профиля пользователя администратором.
    """

    @swagger_auto_schema(
        operation_description="Получить полный профиль пользователя (для админ-панели)",
        responses={200: CMSUserSerializer()},
    )
    def get(self, request, ref=None):
        user = self._resolve_target_user(request, ref=ref)
        if not user:
            return Response(
                {'error': _('Пользователь не найден')},
                status=status.HTTP_404_NOT_FOUND,
            )

        UserProfile.objects.get_or_create(user=user)
        return Response(_build_admin_user_detail(user), status=status.HTTP_200_OK)

    @swagger_auto_schema(
        operation_description="Обновить профиль пользователя (для админ-панели)",
        request_body=UpdateUserProfileSerializer,
        responses={200: CMSUserSerializer(), 400: 'Ошибка валидации данных.'},
    )
    def put(self, request, ref=None):
        user = self._resolve_target_user(request, ref=ref)
        if not user:
            return Response(
                {'error': _('Пользователь не найден')},
                status=status.HTTP_404_NOT_FOUND,
            )

        profile, _ = UserProfile.objects.get_or_create(user=user)
        serializer = UpdateUserProfileSerializer(profile, data=request.data, partial=True)

        if serializer.is_valid():
            serializer.save()
            user = User.objects.select_related('adp_profile').get(pk=user.pk)
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
    def delete(self, request, ref=None):
        user = self._resolve_target_user(request, ref=ref)
        if not user:
            return Response(
                {'error': _('Пользователь не найден')},
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


class AdminUserAvatarView(_AdminUserTargetMixin, MediaApiFileMixin, BaseAPIViewGlobalAdminMixin, BaseAPIView):
    """
    Загрузка и удаление аватара пользователя администратором.
    """
    parser_classes = [JSONParser, MultiPartParser, FormParser]

    @swagger_auto_schema(
        operation_description="Загрузить или заменить аватар пользователя (для админ-панели)",
        responses={200: 'Аватар обновлён', 404: 'Пользователь не найден'},
    )
    def post(self, request, ref=None):
        user = self._resolve_target_user(request, ref=ref, select_related=False)
        if not user:
            return Response(
                {'error': _('Пользователь не найден')},
                status=status.HTTP_404_NOT_FOUND,
            )

        file, file_path = self.get_file_or_path('image')
        if not file and not file_path:
            return Response(
                {'error': _('Файл изображения не передан')},
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
    def delete(self, request, ref=None):
        user = self._resolve_target_user(request, ref=ref, select_related=False)
        if not user:
            return Response(
                {'error': _('Пользователь не найден')},
                status=status.HTTP_404_NOT_FOUND,
            )

        avatar = UserAvatar.objects.filter(user=user).first()
        if avatar:
            avatar.delete()
            return Response(status=status.HTTP_204_NO_CONTENT)

        return Response(
            {'detail': _('Аватар не найден')},
            status=status.HTTP_404_NOT_FOUND,
        )


class AdminUserResetPasswordView(_AdminUserTargetMixin, BaseAPIViewGlobalAdminMixin, BaseAPIView):
    """
    Сброс пароля пользователя администратором.
    Production: случайный пароль + уведомление на email.
    Development: ручная установка пароля при передаче new_password и confirm_password.
    """

    @swagger_auto_schema(
        operation_description="Сбросить пароль пользователя (админ-панель)",
        request_body=AdminResetUserPasswordSerializer,
        responses={200: 'Пароль сброшен или установлен'},
    )
    def post(self, request, ref=None):
        user = self._resolve_target_user(request, ref=ref, select_related=False)
        if not user:
            return Response(
                {'error': _('Пользователь не найден')},
                status=status.HTTP_404_NOT_FOUND,
            )

        if request.user.pk == user.pk:
            return Response(
                {'error': _('Нельзя сбросить пароль собственной учётной записи через эту форму.')},
                status=status.HTTP_400_BAD_REQUEST,
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
                    'message': _('Пароль установлен.'),
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
            email_error = _('У пользователя не указан email — уведомление не отправлено.')

        response_data = {
            'message': _('Пароль сброшен.'),
            'mode': 'system',
            'email_sent': email_sent,
        }
        if email_sent:
            response_data['message'] = _(
                'Пароль сброшен. Пользователю отправлено уведомление.'
            )
        else:
            response_data['warning'] = (
                email_error or _('Не удалось отправить уведомление на email пользователя.')
            )

        return Response(response_data, status=status.HTTP_200_OK)


class AdminUserStatusView(_AdminUserTargetMixin, BaseAPIViewGlobalAdminMixin, BaseAPIView):
    """Приостановка и возобновление учётной записи пользователя."""

    @swagger_auto_schema(
        operation_description=(
            "Установить статус аккаунта (is_active). "
            "При приостановке все сессии пользователя завершаются."
        ),
        request_body=openapi.Schema(
            type=openapi.TYPE_OBJECT,
            required=['is_active'],
            properties={
                'is_active': openapi.Schema(
                    type=openapi.TYPE_BOOLEAN,
                    description='true — возобновить, false — приостановить',
                ),
            },
        ),
        responses={200: CMSUserSerializer(), 400: 'Нельзя изменить статус'},
    )
    def post(self, request, ref=None):
        user = self._resolve_target_user(request, ref=ref, select_related=False)
        if not user:
            return Response(
                {'error': _('Пользователь не найден')},
                status=status.HTTP_404_NOT_FOUND,
            )

        if 'is_active' not in request.data:
            return Response(
                {'error': _('Поле is_active обязательно.')},
                status=status.HTTP_400_BAD_REQUEST,
            )

        raw = request.data.get('is_active')
        if isinstance(raw, bool):
            is_active = raw
        elif isinstance(raw, str) and raw.strip().lower() in ('true', '1', 'false', '0'):
            is_active = raw.strip().lower() in ('true', '1')
        else:
            return Response(
                {'error': _('Поле is_active должно быть булевым значением.')},
                status=status.HTTP_400_BAD_REQUEST,
            )

        if not is_active:
            validation_error = _validate_admin_user_suspend(request, user)
            if validation_error:
                return validation_error

        previous = bool(user.is_active)
        _set_admin_user_active(user, is_active=is_active)
        user = User.objects.select_related('adp_profile').get(pk=user.pk)

        if previous != is_active:
            audit_log(
                'user.activated' if is_active else 'user.suspended',
                request=request,
                severity='security',
                entity={'type': 'user', 'label': user.get_full_name() or user.username},
                meta={'username': user.username, 'is_active': is_active},
            )

        return Response(_build_admin_user_detail(user), status=status.HTTP_200_OK)


class AdminUserDevicesView(_AdminUserTargetMixin, BaseAPIViewGlobalAdminMixin, BaseAPIView):
    """Список активных сессий (устройств) пользователя для админ-панели."""

    @swagger_auto_schema(
        operation_description="Получить активные сессии пользователя (админ-панель)",
        responses={200: UserDeviceSerializer(many=True)},
    )
    def get(self, request, ref=None):
        user = self._resolve_target_user(request, ref=ref, select_related=False)
        if not user:
            return Response(
                {'error': _('Пользователь не найден')},
                status=status.HTTP_404_NOT_FOUND,
            )

        devices = (
            UserDevice.objects
            .filter(user=user, is_active=True)
            .order_by('-last_activity')
        )
        serializer = UserDeviceSerializer(
            devices,
            many=True,
            context={'request': request},
        )
        return Response(serializer.data, status=status.HTTP_200_OK)


class AdminUserDeviceDetailView(_AdminUserTargetMixin, BaseAPIViewGlobalAdminMixin, BaseAPIView):
    """Отзыв одной сессии пользователя администратором."""

    @swagger_auto_schema(
        operation_description="Отозвать сессию пользователя (админ-панель)",
        responses={200: 'Сессия завершена', 404: 'Не найдено'},
    )
    def delete(self, request, ref=None, device_id=None):
        user = self._resolve_target_user(request, ref=ref, select_related=False)
        if not user:
            return Response(
                {'error': _('Пользователь не найден')},
                status=status.HTTP_404_NOT_FOUND,
            )

        device = UserDevice.objects.filter(id=device_id, user=user).first()
        if device is None:
            return Response(
                {'error': _('Сессия не найдена.')},
                status=status.HTTP_404_NOT_FOUND,
            )

        if request.user.pk == user.pk and is_current_device(request, device):
            return Response(
                {'error': _('Нельзя завершить текущую сессию')},
                status=status.HTTP_400_BAD_REQUEST,
            )

        revoke_user_device_session(device)
        audit_log(
            'user.session_revoked',
            request=request,
            severity='security',
            entity={'type': 'user', 'label': user.get_full_name() or user.username},
            meta={'username': user.username, 'device_id': device_id},
        )
        return Response({'message': _('Сессия завершена.')}, status=status.HTTP_200_OK)


class AdminUserRevokeSessionsView(_AdminUserTargetMixin, BaseAPIViewGlobalAdminMixin, BaseAPIView):
    """Отзыв всех сессий пользователя администратором."""

    @swagger_auto_schema(
        operation_description=(
            "Отозвать все сессии пользователя. "
            "Для собственной учётной записи текущая сессия сохраняется."
        ),
        responses={200: 'Сессии отозваны', 404: 'Пользователь не найден'},
    )
    def post(self, request, ref=None):
        user = self._resolve_target_user(request, ref=ref, select_related=False)
        if not user:
            return Response(
                {'error': _('Пользователь не найден')},
                status=status.HTTP_404_NOT_FOUND,
            )

        if request.user.pk == user.pk:
            current_device_id = None
            devices = list(
                UserDevice.objects.filter(user=user, is_active=True).order_by('-last_activity')
            )
            revoked = 0
            for device in devices:
                if is_current_device(request, device):
                    current_device_id = device.id
                    continue
                revoke_user_device_session(device)
                revoked += 1
            audit_log(
                'user.sessions_revoked',
                request=request,
                severity='security',
                entity={'type': 'user', 'label': user.get_full_name() or user.username},
                meta={
                    'username': user.username,
                    'revoked_count': revoked,
                    'kept_current': current_device_id is not None,
                },
            )
            return Response(
                {
                    'message': _('Остальные сессии завершены.'),
                    'revoked_count': revoked,
                },
                status=status.HTTP_200_OK,
            )

        active_count = UserDevice.objects.filter(user=user, is_active=True).count()
        revoke_user_auth(user)
        audit_log(
            'user.sessions_revoked',
            request=request,
            severity='security',
            entity={'type': 'user', 'label': user.get_full_name() or user.username},
            meta={'username': user.username, 'revoked_count': active_count},
        )
        return Response(
            {
                'message': _('Все сессии завершены.'),
                'revoked_count': active_count,
            },
            status=status.HTTP_200_OK,
        )
