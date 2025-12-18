from rest_framework.serializers import (
    ModelSerializer,
    CharField,
    IntegerField,
    ValidationError,
    Serializer,
    ListField,
    SerializerMethodField,
)

from django.contrib.auth.models import User
from django.contrib.auth import authenticate
from src.core.cms.adp.models import (
    UserDevice, UserProfile, Role, RoleGroup, 
    Policy, UserRole, ModulePermission
)

class UserRegistrationValidationSerializer(Serializer):
    first_name = CharField(required=True)
    last_name = CharField(required=True)
    middle_name = CharField(required=False, allow_blank=True)
    username = CharField(required=True)
    email = CharField(required=True)
    password = CharField(write_only=True, style={'input_type': 'password'})

    def validate_username(self, value):
        if User.objects.filter(username=value).exists():
            raise ValidationError("Данный логин уже занят, попробуйте другой.")
        return value

    def validate(self, attrs):
        return attrs


class UserRegistrationSerializer(ModelSerializer):
    password = CharField(
        write_only=True, 
        style={'input_type': 'password'}
    )

    class Meta:
        model = User
        fields = ['first_name', 'last_name', 'middle_name', 'username', 'email', 'password']

    def create(self, validated_data):
        user = User.objects.create_user(
            username=validated_data['username'],
            first_name=validated_data.get('first_name', ''),
            last_name=validated_data.get('last_name', ''),
            middle_name=validated_data.get('middle_name', ''),
            email=validated_data['email'],
            password=validated_data['password'],
        )

        return user
    

class UserLoginSerializer(Serializer):
    username = CharField(max_length=150)
    password = CharField(write_only=True)


class ChangePasswordSerializer(Serializer):
    current_password = CharField(write_only=True, style={'input_type': 'password'})
    new_password = CharField(write_only=True, style={'input_type': 'password'})
    confirm_password = CharField(write_only=True, style={'input_type': 'password'})

    def validate(self, attrs):
        if attrs['new_password'] != attrs['confirm_password']:
            raise ValidationError("Новый пароль и подтверждение не совпадают.")
        
        # Проверка минимальной длины пароля
        if len(attrs['new_password']) < 8:
            raise ValidationError("Пароль должен содержать минимум 8 символов.")
        
        # Проверка на наличие хотя бы одной строчной буквы
        if not any(c.islower() for c in attrs['new_password']):
            raise ValidationError("Пароль должен содержать хотя бы одну букву в нижнем регистре.")
        
        # Проверка на наличие хотя бы одной цифры
        if not any(c.isdigit() for c in attrs['new_password']):
            raise ValidationError("Пароль должен содержать хотя бы одну цифру.")
        
        return attrs

    def validate_current_password(self, value):
        user = self.context['request'].user
        if not authenticate(username=user.username, password=value):
            raise ValidationError("Неверный текущий пароль.")
        return value


class UserDeviceSerializer(ModelSerializer):
    class Meta:
        model = UserDevice
        fields = ['id', 'device_type', 'device_name', 'ip_address', 'city', 'country', 'is_active', 'last_activity', 'created_at']
        read_only_fields = ['id', 'ip_address', 'last_activity', 'created_at']


class CMSUserProfileSerializer(ModelSerializer):
    full_name = CharField(read_only=True)
    
    class Meta:
        model = UserProfile
        fields = [
            'avatar', 'phone', 'website', 'bio', 'country', 'city', 
            'language', 'timezone', 'email_notifications', 'push_notifications', 
            'sms_notifications', 'profile_visibility', 'two_factor_enabled',
            'full_name', 'created_at', 'updated_at'
        ]
        read_only_fields = ['created_at', 'updated_at', 'full_name']


class CMSUserSerializer(ModelSerializer):
    adp_profile = CMSUserProfileSerializer(read_only=True)
    full_name = SerializerMethodField(read_only=True)
    initials_name = SerializerMethodField(read_only=True)
    
    class Meta:
        model = User
        fields = [
            'id',
            'username',
            'email',
            'first_name',
            'last_name',
            'middle_name',
            'full_name',
            'initials_name',
            'is_active',
            'date_joined',
            'adp_profile',
        ]
        read_only_fields = ['id', 'date_joined', 'full_name', 'initials_name']

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


class UpdateUserProfileSerializer(ModelSerializer):
    first_name = CharField(source='user.first_name', required=False, allow_blank=True)
    last_name = CharField(source='user.last_name', required=False, allow_blank=True)
    middle_name = CharField(source='user.middle_name', required=False, allow_blank=True)
    email = CharField(source='user.email', required=False)
    
    class Meta:
        model = UserProfile
        fields = [
            'first_name', 'last_name', 'middle_name', 'email', 'phone', 'website', 'bio', 
            'country', 'city', 'language', 'timezone', 'email_notifications', 
            'push_notifications', 'sms_notifications', 'profile_visibility'
        ]
    
    def update(self, instance, validated_data):
        # Обновляем данные пользователя
        user_data = validated_data.pop('user', {})
        if user_data:
            for attr, value in user_data.items():
                # Для имени, фамилии и отчества разрешаем пустые строки
                if attr in ['first_name', 'last_name', 'middle_name']:
                    # Обрабатываем пробелы как пустые строки
                    if value and value.strip() == '':
                        value = ''
                setattr(instance.user, attr, value)
            instance.user.save()
        
        # Обновляем данные профиля
        for attr, value in validated_data.items():
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
    module_permissions = ModulePermissionSerializer(many=True, read_only=True)


class AdminUserRoleInfoSerializer(Serializer):
    """Сериализатор для представления пользователей и их ролей"""
    user_id = IntegerField()
    username = CharField()
    email = CharField(allow_blank=True)
    full_name = CharField(allow_blank=True)
    role = RoleSerializer(allow_null=True)
    role_groups = RoleGroupSerializer(many=True)