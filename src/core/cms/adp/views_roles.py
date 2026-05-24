"""
Views для управления ролями, политиками и правами доступа.
"""
from rest_framework.response import Response
from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from drf_yasg.utils import swagger_auto_schema
from drf_yasg import openapi

from django.contrib.auth.models import User

from src.core.settings.models import UserAvatar
from src.core.utils.base.base_views import BaseAPIView, BaseAPIViewAuthMixin
from src.core.cms.adp.models import Role, RoleGroup, Policy, UserRole, ModulePermission
from src.core.cms.adp.serializers import (
    RoleSerializer,
    RoleGroupSerializer,
    RoleGroupMinimalSerializer,
    PolicySerializer,
    UserRoleSerializer,
    ModulePermissionSerializer,
    UserPermissionsSerializer,
    AdminUserRoleInfoSerializer,
)
from src.core.cms.adp.services.permissions import PermissionService


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
        if not PermissionService.is_admin(request.user):
            return Response(
                {'error': 'Доступ запрещен. Требуются права администратора.'},
                status=status.HTTP_403_FORBIDDEN
            )
        
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
        operation_description="Получить список пользователей и их ролей",
        responses={200: AdminUserRoleInfoSerializer(many=True)}
    )
    def get(self, request):
        if not PermissionService.is_admin(request.user):
            return Response(
                {'error': 'Доступ запрещен. Требуются права администратора.'},
                status=status.HTTP_403_FORBIDDEN
            )
        
        users = User.objects.select_related('adp_profile', 'avatar').all().order_by('last_name', 'first_name', 'middle_name', 'username')
        result = []

        for user in users:
            user_role = PermissionService.get_user_role(user)
            role = user_role.role if user_role else None
            role_groups = user_role.role_groups.all() if user_role else RoleGroup.objects.none()

            # Формат: Фамилия Имя Отчество
            name_parts = [user.last_name, user.first_name]
            if user.middle_name:
                name_parts.append(user.middle_name)
            full_name = " ".join(part for part in name_parts if part and part.strip()) or user.username

            try:
                avatar = user.avatar
            except UserAvatar.DoesNotExist:
                avatar = None
            avatar_url = None
            if avatar and avatar.image:
                avatar_url = avatar.image.url

            serializer = AdminUserRoleInfoSerializer(instance={
                'user_id': user.id,
                'username': user.username,
                'email': user.email or '',
                'full_name': full_name,
                'first_name': user.first_name or '',
                'last_name': user.last_name or '',
                'date_joined': user.date_joined,
                'role': role,
                'role_groups': list(role_groups),
                'avatar_url': avatar_url,
            })
            result.append(serializer.data)
        
        return Response({'users': result})
