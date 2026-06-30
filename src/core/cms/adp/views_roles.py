"""
Views для управления ролями, политиками и правами доступа.
"""
from rest_framework.response import Response
from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.parsers import MultiPartParser, FormParser, JSONParser
from drf_yasg.utils import swagger_auto_schema
from drf_yasg import openapi

from django.contrib.auth.models import User
from django.db.models import Prefetch, Q
from src.core.settings.models import UserAvatar
from src.core.utils.base.base_views import BaseAPIView, BaseAPIViewAuthMixin
from src.core.utils.mixins import MediaApiFileMixin
from src.core.cms.adp.services.user_search import apply_user_search
from src.core.cms.adp.models import Role, RoleGroup, Policy, UserRole, ModulePermission, UserProfile, UserDevice
from src.core.cms.adp.serializers import (
    RoleSerializer,
    RoleGroupSerializer,
    RoleGroupMinimalSerializer,
    PolicySerializer,
    UserRoleSerializer,
    ModulePermissionSerializer,
    UserPermissionsSerializer,
    AdminUserRoleInfoSerializer,
    CMSUserSerializer,
    UpdateUserProfileSerializer,
    AdminResetUserPasswordSerializer,
)
from src.core.cms.adp.services.permissions import PermissionService
from src.core.cms.adp.services import presence as presence_service
from src.core.cms.adp.services.user_deletion import (
    UserDeletionBlockedError,
    delete_admin_user,
    revoke_user_auth,
)
from src.config.settings.auth import IS_DEVELOPMENT
from src.core.utils.methods import (
    parse_errors_to_dict,
    generate_secure_random_password,
    send_admin_password_reset_notification,
)


ADMIN_FORBIDDEN_MESSAGE = 'Доступ запрещен. Требуются права администратора.'


def _admin_user_forbidden_response():
    return Response(
        {'error': ADMIN_FORBIDDEN_MESSAGE},
        status=status.HTTP_403_FORBIDDEN,
    )


def _require_global_admin(request):
    if not PermissionService.can_manage_users_as_global_admin(request.user):
        return _admin_user_forbidden_response()
    return None


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

    if target_user.is_superuser and not request.user.is_superuser:
        return Response(
            {'error': 'Нельзя удалить суперпользователя.'},
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
    name_parts = [user.last_name, user.first_name]
    middle_name = getattr(user, 'middle_name', None)
    if middle_name:
        name_parts.append(middle_name)
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
    if user_role or getattr(user, 'is_superuser', False):
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
        users_qs = users_qs.filter(presence__connection_count__gt=0)

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
    data['role'] = RoleSerializer(role).data if role else None
    data['role_groups'] = RoleGroupSerializer(role_groups, many=True).data
    data['avatar_url'] = _get_user_avatar_url(user)
    data['password_reset_mode'] = 'manual' if IS_DEVELOPMENT else 'system'
    return data


class RoleListView(BaseAPIViewAuthMixin, BaseAPIView):
    """
    Получение списка ролей и создание новых ролей.
    Только для администраторов.
    """
    permission_classes = [IsAuthenticated]
    
    @swagger_auto_schema(
        operation_description="Получить список всех ролей",
        responses={200: RoleSerializer(many=True)}
    )
    def get(self, request):
        """Получить список всех ролей"""
        if not PermissionService.is_admin(request.user):
            return Response(
                {'error': 'Доступ запрещен. Требуются права администратора.'},
                status=status.HTTP_403_FORBIDDEN
            )
        
        roles = Role.objects.all()
        serializer = RoleSerializer(roles, many=True)
        return Response(serializer.data)
    
    @swagger_auto_schema(
        operation_description="Создать новую роль",
        request_body=RoleSerializer,
        responses={201: RoleSerializer()}
    )
    def post(self, request):
        """Создать новую роль"""
        if not PermissionService.is_admin(request.user):
            return Response(
                {'error': 'Доступ запрещен. Требуются права администратора.'},
                status=status.HTTP_403_FORBIDDEN
            )
        
        serializer = RoleSerializer(data=request.data)
        if serializer.is_valid():
            serializer.save()
            return Response(serializer.data, status=status.HTTP_201_CREATED)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


class RoleDetailView(BaseAPIViewAuthMixin, BaseAPIView):
    """
    Получение, обновление и удаление роли.
    Только для администраторов.
    """
    permission_classes = [IsAuthenticated]
    
    @swagger_auto_schema(
        operation_description="Получить роль по ID",
        responses={200: RoleSerializer()}
    )
    def get(self, request, role_id):
        """Получить роль по ID"""
        if not PermissionService.is_admin(request.user):
            return Response(
                {'error': 'Доступ запрещен. Требуются права администратора.'},
                status=status.HTTP_403_FORBIDDEN
            )
        
        try:
            role = Role.objects.get(id=role_id)
            serializer = RoleSerializer(role)
            return Response(serializer.data)
        except Role.DoesNotExist:
            return Response(
                {'error': 'Роль не найдена'},
                status=status.HTTP_404_NOT_FOUND
            )
    
    @swagger_auto_schema(
        operation_description="Обновить роль",
        request_body=RoleSerializer,
        responses={200: RoleSerializer()}
    )
    def put(self, request, role_id):
        """Обновить роль"""
        if not PermissionService.is_admin(request.user):
            return Response(
                {'error': 'Доступ запрещен. Требуются права администратора.'},
                status=status.HTTP_403_FORBIDDEN
            )
        
        try:
            role = Role.objects.get(id=role_id)
            payload = request.data.copy()
            
            # Нельзя отключать системный статус роли
            if role.is_system and 'is_system' in payload:
                incoming_flag = payload.get('is_system')
                normalized = str(incoming_flag).lower() in ('1', 'true', 'yes')
                if not normalized:
                    return Response(
                        {'error': 'Нельзя изменить системный статус роли'},
                        status=status.HTTP_400_BAD_REQUEST
                    )
                payload.pop('is_system')
            
            serializer = RoleSerializer(role, data=payload, partial=True)
            if serializer.is_valid():
                serializer.save()
                return Response(serializer.data)
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
        except Role.DoesNotExist:
            return Response(
                {'error': 'Роль не найдена'},
                status=status.HTTP_404_NOT_FOUND
            )
    
    @swagger_auto_schema(
        operation_description="Удалить роль",
        responses={204: 'Роль успешно удалена'}
    )
    def delete(self, request, role_id):
        """Удалить роль"""
        if not PermissionService.is_admin(request.user):
            return Response(
                {'error': 'Доступ запрещен. Требуются права администратора.'},
                status=status.HTTP_403_FORBIDDEN
            )
        
        try:
            role = Role.objects.get(id=role_id)
            
            # Нельзя удалять системные роли
            if role.is_system:
                return Response(
                    {'error': 'Нельзя удалить системную роль'},
                    status=status.HTTP_400_BAD_REQUEST
                )
            
            role.delete()
            return Response(status=status.HTTP_204_NO_CONTENT)
        except Role.DoesNotExist:
            return Response(
                {'error': 'Роль не найдена'},
                status=status.HTTP_404_NOT_FOUND
            )


class RoleGroupListView(BaseAPIViewAuthMixin, BaseAPIView):
    """
    Получение списка ролевых групп и создание новых групп.
    Только для администраторов.
    """
    permission_classes = [IsAuthenticated]
    
    @swagger_auto_schema(
        operation_description="Получить список всех ролевых групп. ?minimal=1 — только id, name, parent_role_name.",
        responses={200: RoleGroupSerializer(many=True)}
    )
    def get(self, request):
        """Получить список всех ролевых групп"""
        if not PermissionService.is_admin(request.user):
            return Response(
                {'error': 'Доступ запрещен. Требуются права администратора.'},
                status=status.HTTP_403_FORBIDDEN
            )

        minimal = request.query_params.get('minimal') in ('1', 'true', 'yes')
        groups = RoleGroup.objects.select_related('parent_role').all()
        serializer_class = RoleGroupMinimalSerializer if minimal else RoleGroupSerializer
        serializer = serializer_class(groups, many=True)
        return Response(serializer.data)
    
    @swagger_auto_schema(
        operation_description="Создать новую ролевую группу",
        request_body=RoleGroupSerializer,
        responses={201: RoleGroupSerializer()}
    )
    def post(self, request):
        """Создать новую ролевую группу"""
        if not PermissionService.is_admin(request.user):
            return Response(
                {'error': 'Доступ запрещен. Требуются права администратора.'},
                status=status.HTTP_403_FORBIDDEN
            )
        
        serializer = RoleGroupSerializer(data=request.data)
        if serializer.is_valid():
            serializer.save()
            return Response(serializer.data, status=status.HTTP_201_CREATED)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


class RoleGroupDetailView(BaseAPIViewAuthMixin, BaseAPIView):
    """
    Получение, обновление и удаление ролевой группы.
    Только для администраторов.
    """
    permission_classes = [IsAuthenticated]
    
    def _get_group(self, group_id):
        try:
            return RoleGroup.objects.get(id=group_id)
        except RoleGroup.DoesNotExist:
            return None
    
    @swagger_auto_schema(
        operation_description="Получить ролевую группу по ID",
        responses={200: RoleGroupSerializer()}
    )
    def get(self, request, group_id):
        if not PermissionService.is_admin(request.user):
            return Response(
                {'error': 'Доступ запрещен. Требуются права администратора.'},
                status=status.HTTP_403_FORBIDDEN
            )
        
        group = self._get_group(group_id)
        if not group:
            return Response(
                {'error': 'Ролевая группа не найдена'},
                status=status.HTTP_404_NOT_FOUND
            )
        
        serializer = RoleGroupSerializer(group)
        return Response(serializer.data)
    
    @swagger_auto_schema(
        operation_description="Обновить ролевую группу",
        request_body=RoleGroupSerializer,
        responses={200: RoleGroupSerializer()}
    )
    def put(self, request, group_id):
        if not PermissionService.is_admin(request.user):
            return Response(
                {'error': 'Доступ запрещен. Требуются права администратора.'},
                status=status.HTTP_403_FORBIDDEN
            )
        
        group = self._get_group(group_id)
        if not group:
            return Response(
                {'error': 'Ролевая группа не найдена'},
                status=status.HTTP_404_NOT_FOUND
            )
        
        serializer = RoleGroupSerializer(group, data=request.data, partial=True)
        if serializer.is_valid():
            serializer.save()
            return Response(serializer.data)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
    
    @swagger_auto_schema(
        operation_description="Удалить ролевую группу",
        responses={204: 'Группа удалена'}
    )
    def delete(self, request, group_id):
        if not PermissionService.is_admin(request.user):
            return Response(
                {'error': 'Доступ запрещен. Требуются права администратора.'},
                status=status.HTTP_403_FORBIDDEN
            )
        
        group = self._get_group(group_id)
        if not group:
            return Response(
                {'error': 'Ролевая группа не найдена'},
                status=status.HTTP_404_NOT_FOUND
            )
        
        group.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)


class PolicyListView(BaseAPIViewAuthMixin, BaseAPIView):
    """
    Получение списка политик и создание новых политик.
    Только для администраторов.
    """
    permission_classes = [IsAuthenticated]
    
    @swagger_auto_schema(
        operation_description="Получить список всех политик",
        responses={200: PolicySerializer(many=True)}
    )
    def get(self, request):
        """Получить список всех политик"""
        if not PermissionService.is_admin(request.user):
            return Response(
                {'error': 'Доступ запрещен. Требуются права администратора.'},
                status=status.HTTP_403_FORBIDDEN
            )
        
        policies = Policy.objects.all()
        serializer = PolicySerializer(policies, many=True)
        return Response(serializer.data)
    
    @swagger_auto_schema(
        operation_description="Создать новую политику",
        request_body=PolicySerializer,
        responses={201: PolicySerializer()}
    )
    def post(self, request):
        """Создать новую политику"""
        if not PermissionService.is_admin(request.user):
            return Response(
                {'error': 'Доступ запрещен. Требуются права администратора.'},
                status=status.HTTP_403_FORBIDDEN
            )
        
        serializer = PolicySerializer(data=request.data)
        if serializer.is_valid():
            serializer.save()
            return Response(serializer.data, status=status.HTTP_201_CREATED)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


class PolicyDetailView(BaseAPIViewAuthMixin, BaseAPIView):
    """
    Получение, обновление и удаление политики.
    Только для администраторов.
    """
    permission_classes = [IsAuthenticated]
    
    def _get_policy(self, policy_id):
        try:
            return Policy.objects.get(id=policy_id)
        except Policy.DoesNotExist:
            return None
    
    @swagger_auto_schema(
        operation_description="Получить политику по ID",
        responses={200: PolicySerializer()}
    )
    def get(self, request, policy_id):
        if not PermissionService.is_admin(request.user):
            return Response(
                {'error': 'Доступ запрещен. Требуются права администратора.'},
                status=status.HTTP_403_FORBIDDEN
            )
        
        policy = self._get_policy(policy_id)
        if not policy:
            return Response(
                {'error': 'Политика не найдена'},
                status=status.HTTP_404_NOT_FOUND
            )
        
        serializer = PolicySerializer(policy)
        return Response(serializer.data)
    
    @swagger_auto_schema(
        operation_description="Обновить политику",
        request_body=PolicySerializer,
        responses={200: PolicySerializer()}
    )
    def put(self, request, policy_id):
        if not PermissionService.is_admin(request.user):
            return Response(
                {'error': 'Доступ запрещен. Требуются права администратора.'},
                status=status.HTTP_403_FORBIDDEN
            )
        
        policy = self._get_policy(policy_id)
        if not policy:
            return Response(
                {'error': 'Политика не найдена'},
                status=status.HTTP_404_NOT_FOUND
            )
        
        serializer = PolicySerializer(policy, data=request.data, partial=True)
        if serializer.is_valid():
            serializer.save()
            return Response(serializer.data)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
    
    @swagger_auto_schema(
        operation_description="Удалить политику",
        responses={204: 'Политика удалена'}
    )
    def delete(self, request, policy_id):
        if not PermissionService.is_admin(request.user):
            return Response(
                {'error': 'Доступ запрещен. Требуются права администратора.'},
                status=status.HTTP_403_FORBIDDEN
            )
        
        policy = self._get_policy(policy_id)
        if not policy:
            return Response(
                {'error': 'Политика не найдена'},
                status=status.HTTP_404_NOT_FOUND
            )
        
        policy.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)


class UserRoleAssignView(BaseAPIViewAuthMixin, BaseAPIView):
    """
    Назначение роли пользователю.
    Только для администраторов.
    """
    permission_classes = [IsAuthenticated]
    
    @swagger_auto_schema(
        operation_description="Назначить роль пользователю",
        request_body=openapi.Schema(
            type=openapi.TYPE_OBJECT,
            properties={
                'user_id': openapi.Schema(type=openapi.TYPE_INTEGER, description='ID пользователя'),
                'role_id': openapi.Schema(type=openapi.TYPE_INTEGER, description='ID роли'),
                'role_group_ids': openapi.Schema(
                    type=openapi.TYPE_ARRAY,
                    items=openapi.Schema(type=openapi.TYPE_INTEGER),
                    description='ID ролевых групп (опционально)'
                ),
            },
            required=['user_id', 'role_id']
        ),
        responses={200: UserRoleSerializer()}
    )
    def post(self, request):
        """Назначить роль пользователю"""
        forbidden = _require_global_admin(request)
        if forbidden:
            return forbidden
        
        user_id = request.data.get('user_id')
        role_id = request.data.get('role_id')
        role_group_ids = request.data.get('role_group_ids', [])
        
        try:
            from django.contrib.auth.models import User
            user = User.objects.get(id=user_id)
            role = Role.objects.get(id=role_id)
            
            role_groups = []
            if role_group_ids:
                role_groups = RoleGroup.objects.filter(id__in=role_group_ids)
            
            user_role = PermissionService.assign_role_to_user(
                user=user,
                role=role,
                role_groups=role_groups,
                assigned_by=request.user
            )
            
            serializer = UserRoleSerializer(user_role)
            return Response(serializer.data)
            
        except User.DoesNotExist:
            return Response(
                {'error': 'Пользователь не найден'},
                status=status.HTTP_404_NOT_FOUND
            )
        except Role.DoesNotExist:
            return Response(
                {'error': 'Роль не найдена'},
                status=status.HTTP_404_NOT_FOUND
            )


class UserPermissionsView(BaseAPIViewAuthMixin, BaseAPIView):
    """
    Получение всех прав текущего пользователя.
    """
    permission_classes = [IsAuthenticated]
    
    @swagger_auto_schema(
        operation_description="Получить все права текущего пользователя",
        responses={200: UserPermissionsSerializer()}
    )
    def get(self, request):
        """Получить все права текущего пользователя"""
        permissions = PermissionService.get_user_permissions(request.user)
        serializer = UserPermissionsSerializer(permissions)
        return Response(serializer.data)


class CheckURLAccessView(BaseAPIViewAuthMixin, BaseAPIView):
    """
    Проверка доступа к URL.
    """
    permission_classes = [IsAuthenticated]
    
    @swagger_auto_schema(
        operation_description="Проверить доступ к URL",
        manual_parameters=[
            openapi.Parameter(
                'url',
                openapi.IN_QUERY,
                description="URL для проверки",
                type=openapi.TYPE_STRING,
                required=True
            )
        ],
        responses={
            200: openapi.Schema(
                type=openapi.TYPE_OBJECT,
                properties={
                    'has_access': openapi.Schema(type=openapi.TYPE_BOOLEAN),
                    'url': openapi.Schema(type=openapi.TYPE_STRING),
                }
            )
        }
    )
    def get(self, request):
        """Проверить доступ к URL"""
        url = request.query_params.get('url')
        
        if not url:
            return Response(
                {'error': 'Параметр url обязателен'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        has_access = PermissionService.check_url_access(request.user, url)
        
        return Response({
            'has_access': has_access,
            'url': url
        })


class ModulePermissionListView(BaseAPIViewAuthMixin, BaseAPIView):
    """
    Управление правами модулей для ролевых групп.
    Только для администраторов.
    """
    permission_classes = [IsAuthenticated]
    
    @swagger_auto_schema(
        operation_description="Получить список прав модулей",
        manual_parameters=[
            openapi.Parameter(
                'role_group_id',
                openapi.IN_QUERY,
                description="ID ролевой группы для фильтрации",
                type=openapi.TYPE_INTEGER,
                required=False
            )
        ],
        responses={200: ModulePermissionSerializer(many=True)}
    )
    def get(self, request):
        """Получить список прав модулей"""
        if not PermissionService.is_admin(request.user):
            return Response(
                {'error': 'Доступ запрещен. Требуются права администратора.'},
                status=status.HTTP_403_FORBIDDEN
            )
        
        role_group_id = request.query_params.get('role_group_id')
        
        if role_group_id:
            permissions = ModulePermission.objects.filter(role_group_id=role_group_id)
        else:
            permissions = ModulePermission.objects.all()
        
        serializer = ModulePermissionSerializer(permissions, many=True)
        return Response(serializer.data)
    
    @swagger_auto_schema(
        operation_description="Создать или обновить право модуля",
        request_body=ModulePermissionSerializer,
        responses={201: ModulePermissionSerializer()}
    )
    def post(self, request):
        """Создать или обновить право модуля"""
        if not PermissionService.is_admin(request.user):
            return Response(
                {'error': 'Доступ запрещен. Требуются права администратора.'},
                status=status.HTTP_403_FORBIDDEN
            )
        
        serializer = ModulePermissionSerializer(data=request.data)
        if serializer.is_valid():
            # Проверяем, существует ли уже такое право
            existing = ModulePermission.objects.filter(
                module_name=serializer.validated_data['module_name'],
                permission_key=serializer.validated_data['permission_key'],
                role_group=serializer.validated_data['role_group']
            ).first()
            
            if existing:
                # Обновляем существующее
                serializer = ModulePermissionSerializer(existing, data=request.data, partial=True)
                if serializer.is_valid():
                    serializer.save()
                    return Response(serializer.data)
            else:
                # Создаем новое
                serializer.save()
                return Response(serializer.data, status=status.HTTP_201_CREATED)
        
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


class ModulePermissionDetailView(BaseAPIViewAuthMixin, BaseAPIView):
    """
    Получение, обновление и удаление прав модулей.
    Только для администраторов.
    """
    permission_classes = [IsAuthenticated]
    
    def _get_permission(self, permission_id):
        try:
            return ModulePermission.objects.get(id=permission_id)
        except ModulePermission.DoesNotExist:
            return None
    
    @swagger_auto_schema(
        operation_description="Получить право модуля по ID",
        responses={200: ModulePermissionSerializer()}
    )
    def get(self, request, permission_id):
        if not PermissionService.is_admin(request.user):
            return Response(
                {'error': 'Доступ запрещен. Требуются права администратора.'},
                status=status.HTTP_403_FORBIDDEN
            )
        
        permission = self._get_permission(permission_id)
        if not permission:
            return Response(
                {'error': 'Право модуля не найдено'},
                status=status.HTTP_404_NOT_FOUND
            )
        
        serializer = ModulePermissionSerializer(permission)
        return Response(serializer.data)
    
    @swagger_auto_schema(
        operation_description="Обновить право модуля",
        request_body=ModulePermissionSerializer,
        responses={200: ModulePermissionSerializer()}
    )
    def put(self, request, permission_id):
        if not PermissionService.is_admin(request.user):
            return Response(
                {'error': 'Доступ запрещен. Требуются права администратора.'},
                status=status.HTTP_403_FORBIDDEN
            )
        
        permission = self._get_permission(permission_id)
        if not permission:
            return Response(
                {'error': 'Право модуля не найдено'},
                status=status.HTTP_404_NOT_FOUND
            )
        
        serializer = ModulePermissionSerializer(permission, data=request.data, partial=True)
        if serializer.is_valid():
            serializer.save()
            return Response(serializer.data)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
    
    @swagger_auto_schema(
        operation_description="Удалить право модуля",
        responses={204: 'Право удалено'}
    )
    def delete(self, request, permission_id):
        if not PermissionService.is_admin(request.user):
            return Response(
                {'error': 'Доступ запрещен. Требуются права администратора.'},
                status=status.HTTP_403_FORBIDDEN
            )
        
        permission = self._get_permission(permission_id)
        if not permission:
            return Response(
                {'error': 'Право модуля не найдено'},
                status=status.HTTP_404_NOT_FOUND
            )
        
        permission.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)


class AdminUserRoleListView(BaseAPIViewAuthMixin, BaseAPIView):
    """
    Получение списка пользователей и их ролей для администраторов.
    """
    permission_classes = [IsAuthenticated]
    
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
        forbidden = _require_global_admin(request)
        if forbidden:
            return forbidden

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


class AdminUserDetailView(BaseAPIViewAuthMixin, BaseAPIView):
    """
    Получение и обновление профиля пользователя администратором.
    """
    permission_classes = [IsAuthenticated]

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
        forbidden = _require_global_admin(request)
        if forbidden:
            return forbidden

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
        forbidden = _require_global_admin(request)
        if forbidden:
            return forbidden

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
        forbidden = _require_global_admin(request)
        if forbidden:
            return forbidden

        user = self._get_target_user(user_id)
        if not user:
            return Response(
                {'error': 'Пользователь не найден'},
                status=status.HTTP_404_NOT_FOUND,
            )

        validation_error = _validate_admin_user_deletion(request, user)
        if validation_error:
            return validation_error

        deletion_error = _perform_admin_user_deletion(user)
        if deletion_error:
            return deletion_error

        return Response(status=status.HTTP_204_NO_CONTENT)


class AdminUserAvatarView(MediaApiFileMixin, BaseAPIViewAuthMixin, BaseAPIView):
    """
    Загрузка и удаление аватара пользователя администратором.
    """
    permission_classes = [IsAuthenticated]
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
        forbidden = _require_global_admin(request)
        if forbidden:
            return forbidden

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
        forbidden = _require_global_admin(request)
        if forbidden:
            return forbidden

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


class AdminUserResetPasswordView(BaseAPIViewAuthMixin, BaseAPIView):
    """
    Сброс пароля пользователя администратором.
    Production: случайный пароль + уведомление на email.
    Development: ручная установка пароля при передаче new_password и confirm_password.
    """
    permission_classes = [IsAuthenticated]

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
        forbidden = _require_global_admin(request)
        if forbidden:
            return forbidden

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
