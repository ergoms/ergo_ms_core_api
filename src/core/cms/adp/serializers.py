from rest_framework.serializers import (
    ModelSerializer,
    CharField,
    BooleanField,
    ValidationError,
    Serializer
)

from django.contrib.auth.models import User
from django.contrib.auth import authenticate
from src.core.cms.adp.models import UserDevice, UserProfile

class UserRegistrationValidationSerializer(Serializer):
    first_name = CharField(required=True)
    username = CharField(required=True)
    email = CharField(required=True)
    password = CharField(write_only=True, style={'input_type': 'password'})
    is_superuser = BooleanField(required=True)

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
        fields = ['first_name', 'username', 'email', 'password', 'is_superuser']

    def create(self, validated_data):
        user = User.objects.create_user(
            username=validated_data['username'],
            first_name=validated_data['first_name'],
            email=validated_data['email'],
            password=validated_data['password'],
            is_superuser=validated_data['is_superuser'],
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
    
    class Meta:
        model = User
        fields = ['id', 'username', 'email', 'first_name', 'last_name', 'is_active', 'date_joined', 'adp_profile']
        read_only_fields = ['id', 'date_joined']

class UpdateUserProfileSerializer(ModelSerializer):
    first_name = CharField(source='user.first_name', required=False, allow_blank=True)
    last_name = CharField(source='user.last_name', required=False, allow_blank=True)
    email = CharField(source='user.email', required=False)
    
    class Meta:
        model = UserProfile
        fields = [
            'first_name', 'last_name', 'email', 'phone', 'website', 'bio', 
            'country', 'city', 'language', 'timezone', 'email_notifications', 
            'push_notifications', 'sms_notifications', 'profile_visibility'
        ]
    
    def update(self, instance, validated_data):
        # Обновляем данные пользователя
        user_data = validated_data.pop('user', {})
        if user_data:
            for attr, value in user_data.items():
                # Для имени и фамилии разрешаем пустые строки
                if attr in ['first_name', 'last_name']:
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