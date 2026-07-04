from rest_framework.serializers import (
    ModelSerializer,
    CharField,
    EmailField,
    IntegerField,
    ValidationError,
    Serializer,
    ListField,
    SerializerMethodField,
    DateTimeField,
    BooleanField,
    ChoiceField,
    DictField,
)

from django.contrib.auth.models import User
from django.contrib.auth import authenticate
from src.core.cms.adp.models import (
    UserDevice, UserProfile, Role, RoleGroup,
    Policy, UserRole, ModulePermission, RegistrationInvitation,
)
from src.core.cms.adp.user_agent_utils import (
    format_device_location,
    get_device_type_display,
    parse_user_agent,
)
from src.core.cms.adp.services.registration import RegistrationService
from src.core.cms.adp.password_policy import validate_new_password_pair, validate_password_value
from django.core.exceptions import ValidationError as DjangoValidationError

class UserRegistrationValidationSerializer(Serializer):
    first_name = CharField(required=True)
    last_name = CharField(required=True)
    middle_name = CharField(required=False, allow_blank=True)
    username = CharField(required=True)
    email = CharField(required=True)
    password = CharField(write_only=True, style={'input_type': 'password'})
    invitation_token = CharField(required=False, allow_blank=True, write_only=True)

    def validate_username(self, value):
        if User.objects.filter(username=value).exists():
            raise ValidationError("Данный логин уже занят, попробуйте другой.")
        return value

    def validate_email(self, value):
        normalized = (value or '').strip().lower()
        error = RegistrationService.validate_email_for_registration(normalized)
        if error:
            raise ValidationError(error)
        return normalized

    def validate(self, attrs):
        _validate_registration_access(attrs)
        return attrs


def _validate_registration_access(attrs):
    mode = RegistrationService.get_mode()
    if mode == RegistrationService.MODE_CLOSED:
        raise ValidationError({'message': 'Регистрация в системе отключена.'})

    if mode != RegistrationService.MODE_INVITATION:
        return

    token = (attrs.get('invitation_token') or '').strip()
    if not token:
        raise ValidationError({'invitation_token': 'Для регистрации требуется приглашение.'})

    invitation = RegistrationService.get_valid_invitation(token)
    if not invitation:
        raise ValidationError({'invitation_token': 'Приглашение недействительно или истекло.'})

    email = (attrs.get('email') or '').strip().lower()
    if invitation.email.lower() != email:
        raise ValidationError({'email': 'Email не совпадает с приглашением.'})

    attrs['_invitation'] = invitation


class UserRegistrationSerializer(ModelSerializer):
    password = CharField(
        write_only=True,
        style={'input_type': 'password'},
    )
    invitation_token = CharField(required=False, allow_blank=True, write_only=True)

    class Meta:
        model = User
        fields = [
            'first_name', 'last_name', 'middle_name', 'username', 'email',
            'password', 'invitation_token',
        ]

    def validate_password(self, value):
        try:
            validate_password_value(value)
        except DjangoValidationError as exc:
            raise ValidationError(list(exc.messages))
        return value

    def validate_email(self, value):
        normalized = (value or '').strip().lower()
        error = RegistrationService.validate_email_for_registration(normalized)
        if error:
            raise ValidationError(error)
        return normalized

    def validate(self, attrs):
        _validate_registration_access(attrs)
        return attrs

    def create(self, validated_data):
        invitation = validated_data.pop('_invitation', None)
        validated_data.pop('invitation_token', None)

        user = User.objects.create_user(
            username=validated_data['username'],
            first_name=validated_data.get('first_name', ''),
            last_name=validated_data.get('last_name', ''),
            middle_name=validated_data.get('middle_name', ''),
            email=validated_data['email'],
            password=validated_data['password'],
        )

        if invitation:
            RegistrationService.mark_invitation_used(invitation, user)

        return user
    

class UserLoginSerializer(Serializer):
    username = CharField(max_length=150)
    password = CharField(write_only=True)


class ChangePasswordSerializer(Serializer):
    current_password = CharField(write_only=True, style={'input_type': 'password'})
    new_password = CharField(write_only=True, style={'input_type': 'password'})
    confirm_password = CharField(write_only=True, style={'input_type': 'password'})

    def validate(self, attrs):
        return validate_new_password_pair(attrs)

    def validate_current_password(self, value):
        user = self.context['request'].user
        if not authenticate(username=user.username, password=value):
            raise ValidationError("Неверный текущий пароль.")
        return value


class AdminResetUserPasswordSerializer(Serializer):
    new_password = CharField(
        required=False,
        allow_blank=True,
        write_only=True,
        style={'input_type': 'password'},
    )
    confirm_password = CharField(
        required=False,
        allow_blank=True,
        write_only=True,
        style={'input_type': 'password'},
    )

    def validate(self, attrs):
        new_password = (attrs.get('new_password') or '').strip()
        confirm_password = (attrs.get('confirm_password') or '').strip()

        if not new_password and not confirm_password:
            return attrs

        if not new_password or not confirm_password:
            raise ValidationError('Укажите новый пароль и подтверждение.')

        attrs['new_password'] = new_password
        attrs['confirm_password'] = confirm_password
        return validate_new_password_pair(attrs)


class AdminCreateUserSerializer(Serializer):
    username = CharField(required=True, max_length=150)
    password = CharField(
        required=False,
        allow_blank=True,
        write_only=True,
        style={'input_type': 'password'},
    )
    confirm_password = CharField(
        required=False,
        allow_blank=True,
        write_only=True,
        style={'input_type': 'password'},
    )
    first_name = CharField(required=False, allow_blank=True, default='')
    last_name = CharField(required=False, allow_blank=True, default='')
    middle_name = CharField(required=False, allow_blank=True, default='')
    email = CharField(required=False, allow_blank=True, default='')
    role_id = IntegerField(required=False, allow_null=True)
    role_group_ids = ListField(child=IntegerField(), required=False, default=list)
    send_password_notification = BooleanField(required=False, default=True)

    def validate_username(self, value):
        normalized = (value or '').strip()
        if not normalized:
            raise ValidationError('Логин обязателен.')
        if User.objects.filter(username__iexact=normalized).exists():
            raise ValidationError('Данный логин уже занят, попробуйте другой.')
        return normalized

    def validate_email(self, value):
        normalized = (value or '').strip().lower()
        if not normalized:
            return ''
        error = RegistrationService.validate_email_uniqueness(normalized)
        if error:
            raise ValidationError(error)
        return normalized

    def validate(self, attrs):
        password = (attrs.get('password') or '').strip()
        confirm_password = (attrs.get('confirm_password') or '').strip()
        if not password and not confirm_password:
            return attrs
        if not password or not confirm_password:
            raise ValidationError('Укажите пароль и подтверждение.')
        validate_new_password_pair({
            'new_password': password,
            'confirm_password': confirm_password,
        })
        attrs['password'] = password
        attrs['confirm_password'] = confirm_password
        return attrs


class UserDeviceSerializer(ModelSerializer):
    is_current = SerializerMethodField()
    browser = SerializerMethodField()
    os = SerializerMethodField()
    location = SerializerMethodField()
    device_type_display = SerializerMethodField()

    class Meta:
        model = UserDevice
        fields = [
            'id', 'device_type', 'device_type_display', 'device_name', 'browser', 'os',
            'ip_address', 'city', 'country', 'location', 'is_active', 'is_current',
            'last_activity', 'created_at',
        ]
        read_only_fields = [
            'id', 'device_type', 'device_type_display', 'device_name', 'browser', 'os',
            'ip_address', 'city', 'country', 'location', 'is_active', 'is_current',
            'last_activity', 'created_at',
        ]

    def get_browser(self, obj):
        return parse_user_agent(obj.user_agent)['browser']

    def get_os(self, obj):
        return parse_user_agent(obj.user_agent)['os']

    def get_location(self, obj):
        return format_device_location(obj.city, obj.country)

    def get_device_type_display(self, obj):
        return get_device_type_display(obj.device_type)

    def get_is_current(self, obj):
        request = self.context.get('request')
        if not request:
            return False
        from src.core.cms.adp.services.session_devices import is_current_device

        return is_current_device(request, obj)


class CMSUserProfileSerializer(ModelSerializer):
    """
    Сериализатор профиля пользователя.
    Не включает full_name, так как он уже есть в корне объекта пользователя.
    Не включает avatar, так как аватары загружаются через отдельный API (userAvatars).
    Не включает updated_at, так как это метаданное не используется в UI.
    Не включает настройки безопасности и уведомлений, так как они используются в отдельных разделах.
    """
    
    class Meta:
        model = UserProfile
        fields = [
            'phone', 'bio',
            'language', 'timezone', 'created_at'
        ]
        read_only_fields = ['created_at']


class CMSUserMenuSerializer(ModelSerializer):
    """
    Минимальный сериализатор пользователя для меню.
    Возвращает только необходимые данные для отображения в боковом меню:
    username, email, first_name, middle_name, full_name, initials_name.
    Используется в эндпоинте /api/cms/adp/user-menu-data/
    """
    full_name = SerializerMethodField(read_only=True)
    initials_name = SerializerMethodField(read_only=True)
    
    class Meta:
        model = User
        fields = [
            'id',
            'username',
            'email',
            'first_name',
            'middle_name',
            'full_name',
            'initials_name',
        ]
        read_only_fields = ['id', 'full_name', 'initials_name']

    def get_full_name(self, obj):
        """
        Возвращаем полное имя пользователя через метод Django User.get_full_name().
        """
        full_name = obj.get_full_name()
        return full_name if isinstance(full_name, str) else str(full_name or '')

    def get_initials_name(self, obj):
        """
        Возвращаем инициалы пользователя через метод кастомного User.get_initials_name().
        """
        initials = obj.get_initials_name()
        return initials if isinstance(initials, str) else str(initials or '')


class CMSUserBasicSerializer(ModelSerializer):
    """
    Легковесный сериализатор пользователя без профиля.
    Используется для быстрой проверки токена и базовой инициализации.
    Не включает full_name и initials_name, так как они используются только в меню через отдельный эндпоинт.
    Не включает id, так как он доступен через userStore.user.id (загружается через меню).
    """
    
    class Meta:
        model = User
        fields = [
            'username',
            'email',
            'first_name',
            'last_name',
            'middle_name',
            'is_active',
            'date_joined',
        ]
        read_only_fields = ['date_joined']


class CMSUserSerializer(CMSUserBasicSerializer):
    """
    Полный сериализатор пользователя с профилем.
    Используется для получения полных данных пользователя.
    """
    adp_profile = CMSUserProfileSerializer(read_only=True)
    
    class Meta(CMSUserBasicSerializer.Meta):
        fields = CMSUserBasicSerializer.Meta.fields + ['adp_profile']


class UpdateUserProfileSerializer(ModelSerializer):
    first_name = CharField(source='user.first_name', required=False, allow_blank=True)
    last_name = CharField(source='user.last_name', required=False, allow_blank=True)
    middle_name = CharField(source='user.middle_name', required=False, allow_blank=True)
    email = EmailField(source='user.email', required=False, allow_blank=True)
    phone = CharField(required=False, allow_blank=True, allow_null=True)
    bio = CharField(required=False, allow_blank=True, allow_null=True)

    class Meta:
        model = UserProfile
        fields = [
            'first_name', 'last_name', 'middle_name', 'email', 'phone', 'bio',
            'language', 'timezone'
        ]

    def validate_email(self, value):
        if value is None:
            return value

        normalized = value.strip().lower()
        if not normalized:
            return ''

        exclude_user_id = self.instance.user_id if self.instance is not None else None
        error = RegistrationService.validate_email_uniqueness(
            normalized,
            exclude_user_id=exclude_user_id,
        )
        if error:
            raise ValidationError(error)

        return normalized

    def _normalize_blank_profile_value(self, value):
        if value is None:
            return None
        if isinstance(value, str) and not value.strip():
            return None
        return value

    def update(self, instance, validated_data):
        user_data = validated_data.pop('user', {})
        if user_data:
            for attr, value in user_data.items():
                if attr in ['first_name', 'last_name', 'middle_name']:
                    if isinstance(value, str) and not value.strip():
                        value = ''
                setattr(instance.user, attr, value)
            instance.user.save()

        nullable_profile_fields = ['phone', 'bio']
        for attr, value in validated_data.items():
            if attr in nullable_profile_fields:
                value = self._normalize_blank_profile_value(value)
            setattr(instance, attr, value)
        instance.save()

        return instance


# Сериализаторы для системы ролей и политик

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

    class Meta:
        model = RoleGroup
        fields = [
            'id', 'name', 'parent_role', 'parent_role_name',
            'description', 'is_active', 'created_at', 'updated_at'
        ]
        read_only_fields = ['id', 'created_at', 'updated_at']


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
        # Проверка, что политика привязана либо к роли, либо к группе
        role = attrs.get('role')
        role_group = attrs.get('role_group')
        
        if not role and not role_group:
            raise ValidationError('Политика должна быть привязана к роли или ролевой группе')
        if role and role_group:
            raise ValidationError('Политика не может быть одновременно привязана к роли и ролевой группе')
        
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
    username = CharField()
    email = CharField(allow_blank=True)
    full_name = CharField(allow_blank=True)
    first_name = CharField(allow_blank=True, required=False)
    last_name = CharField(allow_blank=True, required=False)
    date_joined = DateTimeField(allow_null=True, required=False)
    last_login = DateTimeField(allow_null=True, required=False)
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


class RegistrationInvitationSerializer(Serializer):
    id = IntegerField(read_only=True)
    email = CharField(read_only=True)
    token = CharField(read_only=True)
    invite_url = SerializerMethodField()
    status = SerializerMethodField()
    note = CharField(read_only=True)
    invited_by_id = IntegerField(read_only=True, allow_null=True)
    invited_by_name = SerializerMethodField()
    expires_at = DateTimeField(read_only=True)
    used_at = DateTimeField(read_only=True, allow_null=True)
    created_at = DateTimeField(read_only=True)

    def get_invite_url(self, obj):
        return RegistrationService.build_invitation_url(obj.token)

    def get_status(self, obj):
        return RegistrationService.get_invitation_status(obj)

    def get_invited_by_name(self, obj):
        if not obj.invited_by:
            return ''
        return obj.invited_by.get_full_name() or obj.invited_by.username


class CreateRegistrationInvitationSerializer(Serializer):
    email = CharField(required=True)
    note = CharField(required=False, allow_blank=True, default='')
    send_email = BooleanField(required=False, default=False)

    def validate_email(self, value):
        normalized = value.strip().lower()
        error = RegistrationService.validate_email_for_invitation(normalized)
        if error:
            raise ValidationError(error)
        return normalized


class BulkCreateRegistrationInvitationsSerializer(Serializer):
    emails = ListField(child=CharField(), allow_empty=False, max_length=500)
    note = CharField(required=False, allow_blank=True, default='')
    send_email = BooleanField(required=False, default=False)


class BulkSendRegistrationInvitationsSerializer(Serializer):
    invitation_ids = ListField(child=IntegerField(), allow_empty=False, max_length=500)


class ClearRegistrationInvitationsSerializer(Serializer):
    SCOPE_INACTIVE = 'inactive'
    SCOPE_ALL = 'all'

    scope = ChoiceField(
        choices=[(SCOPE_INACTIVE, 'inactive'), (SCOPE_ALL, 'all')],
        default=SCOPE_INACTIVE,
        required=False,
    )


class ValidateInvitationSerializer(Serializer):
    valid = BooleanField(read_only=True)
    email = CharField(read_only=True, allow_null=True)
    expires_at = DateTimeField(read_only=True, allow_null=True)
    status = CharField(read_only=True, allow_null=True)