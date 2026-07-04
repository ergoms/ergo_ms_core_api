"""
Views для управления ролями, политиками и правами доступа.
"""
from rest_framework.response import Response
from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from drf_yasg.utils import swagger_auto_schema
from drf_yasg import openapi

from django.contrib.auth.models import User
from src.core.utils.base.base_views import BaseAPIView, BaseAPIViewAuthMixin, BaseAPIViewGlobalAdminMixin
from src.core.cms.adp.models import Role, RoleGroup, Policy, UserRole, ModulePermission
from src.core.cms.adp.serializers import (
    RoleSerializer,
    RoleGroupSerializer,
    RoleGroupMinimalSerializer,
    PolicySerializer,
    UserRoleSerializer,
    ModulePermissionSerializer,
    UserPermissionsSerializer,
)
from src.core.cms.adp.services.permissions import PermissionService, RoleAssignmentError
from src.core.utils.methods import parse_errors_to_dict


def _audit(action, *, request=None, severity='info', entity=None, changes=None, meta=None):
    """Запись действия администрирования в единый журнал (безопасно к сбоям)."""
    from src.core.audit.shortcuts import audit_log
    audit_log(
        action,
        source_module='core.cms.adp',
        request=request,
        severity=severity,
        entity=entity,
        changes=changes,
        meta=meta,
    )


def _require_global_admin(request):
    """403 Response, если пользователь не глобальный администратор; иначе None."""
    if PermissionService.can_manage_users_as_global_admin(request.user):
        return None
    return Response({'detail': 'Forbidden'}, status=status.HTTP_403_FORBIDDEN)


class RoleListView(BaseAPIViewGlobalAdminMixin, BaseAPIView):
    """
    Получение списка ролей и создание новых ролей.
    Только для администраторов.
    """
    
    @swagger_auto_schema(
        operation_description="Получить список всех ролей",
        responses={200: RoleSerializer(many=True)}
    )
    def get(self, request):
        """Получить список всех ролей"""
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
        serializer = RoleSerializer(data=request.data)
        if serializer.is_valid():
            role = serializer.save()
            _audit('role.created', request=request, severity='security',
                   entity={'type': 'role', 'label': role.name})
            return Response(serializer.data, status=status.HTTP_201_CREATED)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


class RoleDetailView(BaseAPIViewGlobalAdminMixin, BaseAPIView):
    """
    Получение, обновление и удаление роли.
    Только для администраторов.
    """
    
    @swagger_auto_schema(
        operation_description="Получить роль по ID",
        responses={200: RoleSerializer()}
    )
    def get(self, request, role_id):
        """Получить роль по ID"""
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
                _audit('role.updated', request=request, severity='security',
                       entity={'type': 'role', 'label': role.name})
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
        try:
            role = Role.objects.get(id=role_id)
            
            # Нельзя удалять системные роли
            if role.is_system:
                return Response(
                    {'error': 'Нельзя удалить системную роль'},
                    status=status.HTTP_400_BAD_REQUEST
                )
            
            role_name = role.name
            role.delete()
            _audit('role.deleted', request=request, severity='security',
                   entity={'type': 'role', 'label': role_name})
            return Response(status=status.HTTP_204_NO_CONTENT)
        except Role.DoesNotExist:
            return Response(
                {'error': 'Роль не найдена'},
                status=status.HTTP_404_NOT_FOUND
            )


class RoleGroupListView(BaseAPIViewGlobalAdminMixin, BaseAPIView):
    """
    Получение списка ролевых групп и создание новых групп.
    Только для администраторов.
    """
    
    @swagger_auto_schema(
        operation_description="Получить список всех ролевых групп. ?minimal=1 — только id, name, parent_role_name.",
        responses={200: RoleGroupSerializer(many=True)}
    )
    def get(self, request):
        """Получить список всех ролевых групп"""
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
        serializer = RoleGroupSerializer(data=request.data)
        if serializer.is_valid():
            group = serializer.save()
            _audit('role_group.created', request=request, severity='security',
                   entity={'type': 'role_group', 'label': getattr(group, 'name', '')})
            return Response(serializer.data, status=status.HTTP_201_CREATED)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


class RoleGroupDetailView(BaseAPIViewGlobalAdminMixin, BaseAPIView):
    """
    Получение, обновление и удаление ролевой группы.
    Только для администраторов.
    """
    
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
        group = self._get_group(group_id)
        if not group:
            return Response(
                {'error': 'Ролевая группа не найдена'},
                status=status.HTTP_404_NOT_FOUND
            )
        
        serializer = RoleGroupSerializer(group, data=request.data, partial=True)
        if serializer.is_valid():
            serializer.save()
            _audit('role_group.updated', request=request, severity='security',
                   entity={'type': 'role_group', 'label': getattr(group, 'name', '')})
            return Response(serializer.data)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
    
    @swagger_auto_schema(
        operation_description="Удалить ролевую группу",
        responses={204: 'Группа удалена'}
    )
    def delete(self, request, group_id):
        group = self._get_group(group_id)
        if not group:
            return Response(
                {'error': 'Ролевая группа не найдена'},
                status=status.HTTP_404_NOT_FOUND
            )
        
        group_name = getattr(group, 'name', '')
        group.delete()
        _audit('role_group.deleted', request=request, severity='security',
               entity={'type': 'role_group', 'label': group_name})
        return Response(status=status.HTTP_204_NO_CONTENT)


class PolicyListView(BaseAPIViewGlobalAdminMixin, BaseAPIView):
    """
    Получение списка политик и создание новых политик.
    Только для администраторов.
    """
    
    @swagger_auto_schema(
        operation_description="Получить список всех политик",
        responses={200: PolicySerializer(many=True)}
    )
    def get(self, request):
        """Получить список всех политик"""
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
        serializer = PolicySerializer(data=request.data)
        if serializer.is_valid():
            policy = serializer.save()
            _audit('policy.created', request=request, severity='security',
                   entity={'type': 'policy', 'label': str(policy)})
            return Response(serializer.data, status=status.HTTP_201_CREATED)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


class PolicyDetailView(BaseAPIViewGlobalAdminMixin, BaseAPIView):
    """
    Получение, обновление и удаление политики.
    Только для администраторов.
    """
    
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
        policy = self._get_policy(policy_id)
        if not policy:
            return Response(
                {'error': 'Политика не найдена'},
                status=status.HTTP_404_NOT_FOUND
            )
        
        serializer = PolicySerializer(policy, data=request.data, partial=True)
        if serializer.is_valid():
            serializer.save()
            _audit('policy.updated', request=request, severity='security',
                   entity={'type': 'policy', 'label': str(policy)})
            return Response(serializer.data)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
    
    @swagger_auto_schema(
        operation_description="Удалить политику",
        responses={204: 'Политика удалена'}
    )
    def delete(self, request, policy_id):
        policy = self._get_policy(policy_id)
        if not policy:
            return Response(
                {'error': 'Политика не найдена'},
                status=status.HTTP_404_NOT_FOUND
            )
        
        policy_label = str(policy)
        policy.delete()
        _audit('policy.deleted', request=request, severity='security',
               entity={'type': 'policy', 'label': policy_label})
        return Response(status=status.HTTP_204_NO_CONTENT)


class UserRoleAssignView(BaseAPIViewGlobalAdminMixin, BaseAPIView):
    """
    Назначение роли пользователю.
    Только для администраторов.
    """
    
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

            try:
                from src.core.integrations import bridge
                bridge.call(
                    'audit.record',
                    action='user.role_assigned',
                    source_module='core.cms.adp',
                    request=request,
                    severity='security',
                    entity={'type': 'user', 'ref': '', 'label': user.get_full_name() or user.username},
                    changes=[{'field': 'role', 'label': 'Роль', 'old': '', 'new': role.name}],
                    meta={'target_username': user.username},
                )
            except Exception:
                pass

            serializer = UserRoleSerializer(user_role)
            return Response(serializer.data)

        except RoleAssignmentError as exc:
            return Response(
                {'error': exc.message},
                status=status.HTTP_400_BAD_REQUEST,
            )
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


class ModulePermissionListView(BaseAPIViewGlobalAdminMixin, BaseAPIView):
    """
    Управление правами модулей для ролевых групп.
    Только для администраторов.
    """
    
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
                    _audit('module_permission.updated', request=request, severity='security',
                           entity={'type': 'module_permission', 'label': str(existing)})
                    return Response(serializer.data)
            else:
                # Создаем новое
                perm = serializer.save()
                _audit('module_permission.created', request=request, severity='security',
                       entity={'type': 'module_permission', 'label': str(perm)})
                return Response(serializer.data, status=status.HTTP_201_CREATED)
        
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


class ModulePermissionDetailView(BaseAPIViewGlobalAdminMixin, BaseAPIView):
    """
    Получение, обновление и удаление прав модулей.
    Только для администраторов.
    """
    
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
        permission = self._get_permission(permission_id)
        if not permission:
            return Response(
                {'error': 'Право модуля не найдено'},
                status=status.HTTP_404_NOT_FOUND
            )
        
        serializer = ModulePermissionSerializer(permission, data=request.data, partial=True)
        if serializer.is_valid():
            serializer.save()
            _audit('module_permission.updated', request=request, severity='security',
                   entity={'type': 'module_permission', 'label': str(permission)})
            return Response(serializer.data)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
    
    @swagger_auto_schema(
        operation_description="Удалить право модуля",
        responses={204: 'Право удалено'}
    )
    def delete(self, request, permission_id):
        permission = self._get_permission(permission_id)
        if not permission:
            return Response(
                {'error': 'Право модуля не найдено'},
                status=status.HTTP_404_NOT_FOUND
            )
        
        permission_label = str(permission)
        permission.delete()
        _audit('module_permission.deleted', request=request, severity='security',
               entity={'type': 'module_permission', 'label': permission_label})
        return Response(status=status.HTTP_204_NO_CONTENT)


