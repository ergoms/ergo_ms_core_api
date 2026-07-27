from django.utils.translation import gettext as _
from rest_framework.serializers import (
    BooleanField,
    CharField,
    DateTimeField,
    DictField,
    IntegerField,
    ListField,
    ModelSerializer,
    PrimaryKeyRelatedField,
    Serializer,
    SerializerMethodField,
    ValidationError,
)

from src.core.cms.adp.models import (
    ModulePermission,
    Policy,
    Role,
    RoleGroup,
    UserRole,
)


class RoleSerializer(ModelSerializer):
    """Сериализатор для ролей"""
    role_type = CharField(read_only=True)
    role_type_display = CharField(source='get_role_type_display', read_only=True)

    class Meta:
        model = Role
        fields = [
            'id', 'name', 'role_type', 'role_type_display',
            'description', 'is_system', 'created_at', 'updated_at'
        ]
        read_only_fields = ['id', 'created_at', 'updated_at']

    def validate(self, attrs):
        role_type_value = self.initial_data.get('role_type')
        if 'is_system' not in attrs and role_type_value is not None:
            attrs['is_system'] = str(role_type_value).lower() in ('admin', 'true', '1')
        return attrs


class RoleGroupSerializer(ModelSerializer):
    """Сериализатор для ролевых групп"""
    parent_role_name = CharField(source='parent_role.name', read_only=True)
    parent_role = PrimaryKeyRelatedField(queryset=Role.objects.all())

    class Meta:
        model = RoleGroup
        fields = [
            'id', 'name', 'parent_role', 'parent_role_name',
            'description', 'is_active', 'created_at', 'updated_at'
        ]
        read_only_fields = ['id', 'created_at', 'updated_at']

    def validate_parent_role(self, value):
        if value.is_system:
            raise ValidationError(_('Ролевую группу нельзя привязать к системной роли «Администратор». '
                'У администраторов полный доступ без ролевых групп. '
                'Выберите роль «Пользователь» или другую пользовательскую роль.'))
        return value


class RoleListMinimalSerializer(ModelSerializer):
    """Минимальный сериализатор роли для списка пользователей (id, name)."""

    class Meta:
        model = Role
        fields = ['id', 'name']


class RoleGroupMinimalSerializer(ModelSerializer):
    """Минимальный сериализатор для выбора ролевой группы (id, name, parent_role_name)."""
    parent_role_name = CharField(source='parent_role.name', read_only=True)

    class Meta:
        model = RoleGroup
        fields = ['id', 'name', 'parent_role_name']


class RoleGroupListMinimalSerializer(ModelSerializer):
    """Минимальный сериализатор ролевой группы для списка пользователей (id, name)."""

    class Meta:
        model = RoleGroup
        fields = ['id', 'name']


class PolicySerializer(ModelSerializer):
    """Сериализатор для политик"""
    policy_type_display = CharField(source='get_policy_type_display', read_only=True)
    action_display = CharField(source='get_action_display', read_only=True)
    role_name = CharField(source='role.name', read_only=True, allow_null=True)
    role_group_name = CharField(source='role_group.name', read_only=True, allow_null=True)

    class Meta:
        model = Policy
        fields = [
            'id', 'name', 'policy_type', 'policy_type_display',
            'action', 'action_display', 'resource_path', 'is_pattern',
            'role', 'role_name', 'role_group', 'role_group_name',
            'description', 'is_active', 'priority',
            'created_at', 'updated_at'
        ]
        read_only_fields = ['id', 'created_at', 'updated_at']

    def validate(self, attrs):
        role = attrs.get('role')
        role_group = attrs.get('role_group')

        if not role and not role_group:
            raise ValidationError(_('Политика должна быть привязана к роли или ролевой группе'))
        if role and role_group:
            raise ValidationError(_('Политика не может быть одновременно привязана к роли и ролевой группе'))

        return attrs


class UserRoleSerializer(ModelSerializer):
    """Сериализатор для назначения ролей пользователям"""
    username = CharField(source='user.username', read_only=True)
    role_name = CharField(source='role.name', read_only=True)
    assigned_by_username = CharField(source='assigned_by.username', read_only=True, allow_null=True)
    role_groups_data = RoleGroupSerializer(source='role_groups', many=True, read_only=True)

    class Meta:
        model = UserRole
        ref_name = 'CmsAdpUserRole'
        fields = [
            'id', 'user', 'username', 'role', 'role_name',
            'role_groups', 'role_groups_data', 'is_active',
            'assigned_at', 'assigned_by', 'assigned_by_username'
        ]
        read_only_fields = ['id', 'assigned_at']


class ModulePermissionSerializer(ModelSerializer):
    """Сериализатор для прав доступа к модулям"""
    role_group_name = CharField(source='role_group.name', read_only=True)

    class Meta:
        model = ModulePermission
        fields = [
            'id', 'module_name', 'permission_key', 'permission_name',
            'description', 'role_group', 'role_group_name',
            'is_granted', 'created_at', 'updated_at'
        ]
        read_only_fields = ['id', 'created_at', 'updated_at']


class UserPermissionsSerializer(Serializer):
    """Сериализатор для получения всех прав пользователя"""
    user_id = CharField(read_only=True)
    username = CharField(read_only=True)
    role = RoleSerializer(read_only=True)
    role_groups = RoleGroupSerializer(many=True, read_only=True)
    allowed_urls = ListField(child=CharField(), read_only=True)
    denied_urls = ListField(child=CharField(), read_only=True)
    is_global_admin = BooleanField(read_only=True, default=False)
    module_permissions = ModulePermissionSerializer(many=True, read_only=True)


class AdminUserRoleInfoSerializer(Serializer):
    """Сериализатор для представления пользователей и их ролей"""
    user_id = IntegerField()
    public_id = CharField(allow_null=True, required=False)
    username = CharField()
    email = CharField(allow_blank=True)
    full_name = CharField(allow_blank=True)
    first_name = CharField(allow_blank=True, required=False)
    last_name = CharField(allow_blank=True, required=False)
    date_joined = DateTimeField(allow_null=True, required=False)
    last_login = DateTimeField(allow_null=True, required=False)
    is_active = BooleanField(required=False, default=True)
    is_online = BooleanField(required=False)
    last_seen = DateTimeField(allow_null=True, required=False)
    role = RoleListMinimalSerializer(allow_null=True)
    role_groups = RoleGroupListMinimalSerializer(many=True)
    avatar_url = CharField(allow_blank=True, allow_null=True, required=False)


class UserPresenceEntrySerializer(Serializer):
    is_online = BooleanField()
    last_seen = DateTimeField(allow_null=True, required=False)


class UserPresenceBatchResponseSerializer(Serializer):
    presence = DictField(child=UserPresenceEntrySerializer())
