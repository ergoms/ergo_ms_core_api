from django.utils.translation import gettext as _
from rest_framework import serializers

from .models import UserAvatar
from src.core.utils.mixins import validate_media_path
from .models import (
    Theme,
    EmailSettings,
)
from src.core.settings.services.user_theme_preference import set_theme_available


class ThemeSerializer(serializers.ModelSerializer):
    """Сериализатор для тем оформления"""
    
    class Meta:
        model = Theme
        fields = [
            'id', 'name', 'description', 'author', 'base_theme',
            'module_key', 'module_pair', 'module_tokens',
            'is_active', 'is_default', 'is_available', 'is_system',
            'colors', 'bootstrap_colors',
            'created_at', 'updated_at'
        ]
        read_only_fields = ['created_at', 'updated_at', 'is_system']
        # Уникальное имя схемы для Swagger, чтобы не конфликтовать с LmsThemeSerializer
        ref_name = 'CoreThemeSerializer'
    
    def validate(self, data):
        if self.instance and self.instance.is_system:
            # Системные темы (сайт и модуль) — палитра и описание редактируемы;
            # is_system остаётся read_only; привязку к модулю у тем сайта не меняем.
            allowed_fields = {
                'is_active',
                'is_default',
                'is_available',
                'name',
                'description',
                'author',
                'colors',
                'bootstrap_colors',
                'module_tokens',
                'base_theme',
            }
            if self.instance.module_key:
                allowed_fields |= {'module_key', 'module_pair'}
            changed_fields = set(data.keys()) - allowed_fields
            if changed_fields:
                raise serializers.ValidationError(
                    'Нельзя изменять служебные поля системной темы.'
                )

        instance = self.instance
        module_key = data.get('module_key', getattr(instance, 'module_key', None))
        base_theme = data.get('base_theme', getattr(instance, 'base_theme', None))
        if module_key and base_theme not in ('light', 'dark'):
            raise serializers.ValidationError({
                'base_theme': 'У модульной темы вариант может быть только light или dark.',
            })
        return data

    def update(self, instance, validated_data):
        available = validated_data.pop('is_available', None)
        instance = super().update(instance, validated_data)
        if available is not None:
            try:
                instance = set_theme_available(instance, bool(available))
            except ValueError as exc:
                raise serializers.ValidationError({'is_available': str(exc)}) from exc
        return instance


class UserThemePreferenceSerializer(serializers.Serializer):
    selected_theme_id = serializers.IntegerField(allow_null=True, required=False)
    favorite_ids = serializers.ListField(
        child=serializers.IntegerField(),
        required=False,
    )
    default_theme_id = serializers.IntegerField(allow_null=True, required=False, read_only=True)

    class Meta:
        ref_name = 'UserThemePreferenceSerializer'


class EmailSettingsSerializer(serializers.ModelSerializer):
    password = serializers.CharField(
        write_only=True,
        required=False,
        allow_blank=True,
        style={'input_type': 'password'},
    )
    password_set = serializers.SerializerMethodField()

    class Meta:
        model = EmailSettings
        fields = (
            'id',
            'smtp_host',
            'smtp_port',
            'use_tls',
            'username',
            'password',
            'default_from',
            'password_set',
        )
        read_only_fields = ('password_set',)

    def get_password_set(self, obj) -> bool:
        return bool(obj.password)

    def create(self, validated_data):
        password = validated_data.pop('password', None)
        instance = EmailSettings(**validated_data)
        if password is not None:
            instance.set_password_plain(password)
        instance.save()
        return instance

    def update(self, instance, validated_data):
        password = validated_data.pop('password', None)
        for attr, value in validated_data.items():
            setattr(instance, attr, value)
        if password is not None and password != '':
            instance.set_password_plain(password)
        instance.save()
        return instance

class UserAvatarSerializer(serializers.ModelSerializer):
    user = serializers.PrimaryKeyRelatedField(read_only=True)
    image_path = serializers.CharField(write_only=True, required=False)

    class Meta:
        model = UserAvatar
        fields = ['id', 'user', 'image', 'image_path', 'uploaded_at']
        extra_kwargs = {'image': {'required': False}}

    def validate_image_path(self, value):
        if value:
            return validate_media_path(value, 'image')
        return value

    def validate(self, attrs):
        if self.instance is None and not attrs.get('image') and not attrs.get('image_path'):
            raise serializers.ValidationError(_('Необходимо указать image или image_path'))
        return attrs

    def create(self, validated_data):
        image_path = validated_data.pop('image_path', None)
        uploaded_file = validated_data.pop('image', None)
        instance = UserAvatar.objects.create(**validated_data)
        if image_path:
            instance.image.name = image_path
            instance.save(update_fields=['image'])
        elif uploaded_file:
            instance.image.save(uploaded_file.name, uploaded_file, save=True)
        return instance

class UserAvatarListSerializer(serializers.ModelSerializer):
    """Легковесный сериализатор для списка аватаров (только URL изображения)"""
    class Meta:
        model = UserAvatar
        fields = ['image']
