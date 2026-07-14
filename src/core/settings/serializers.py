from rest_framework import serializers

from .models import UserAvatar
from src.core.utils.mixins import validate_media_path
from .models import (
    Theme,
    SecuritySettings, MediaSettings, PermalinkSettings, EmailSettings
)

class ThemeSerializer(serializers.ModelSerializer):
    """Сериализатор для тем оформления"""
    
    class Meta:
        model = Theme
        fields = [
            'id', 'name', 'description', 'author', 'base_theme',
            'module_key', 'module_pair', 'module_tokens',
            'is_active', 'is_default', 'is_system',
            'colors', 'bootstrap_colors',
            'created_at', 'updated_at'
        ]
        read_only_fields = ['created_at', 'updated_at', 'is_system']
        # Уникальное имя схемы для Swagger, чтобы не конфликтовать с LmsThemeSerializer
        ref_name = 'CoreThemeSerializer'
    
    def validate(self, data):
        if self.instance and self.instance.is_system:
            if self.instance.module_key:
                allowed_fields = {
                    'is_active',
                    'is_default',
                    'name',
                    'description',
                    'author',
                    'colors',
                    'bootstrap_colors',
                    'module_tokens',
                    'base_theme',
                    'module_key',
                    'module_pair',
                }
            else:
                allowed_fields = {'is_active', 'is_default'}
            changed_fields = set(data.keys()) - allowed_fields
            if changed_fields:
                raise serializers.ValidationError(
                    'Нельзя изменять структуру системной темы. '
                    'Для темы сайта создайте копию; для модуля можно менять палитру и описание.'
                )

        instance = self.instance
        module_key = data.get('module_key', getattr(instance, 'module_key', None))
        base_theme = data.get('base_theme', getattr(instance, 'base_theme', None))
        if module_key and base_theme not in ('light', 'dark'):
            raise serializers.ValidationError({
                'base_theme': 'У модульной темы вариант может быть только light или dark.',
            })
        return data


class SecuritySettingsSerializer(serializers.ModelSerializer):
    class Meta:
        model = SecuritySettings
        fields = '__all__'

class MediaSettingsSerializer(serializers.ModelSerializer):
    class Meta:
        model = MediaSettings
        fields = '__all__'

class PermalinkSettingsSerializer(serializers.ModelSerializer):
    class Meta:
        model = PermalinkSettings
        fields = '__all__'

class EmailSettingsSerializer(serializers.ModelSerializer):
    class Meta:
        model = EmailSettings
        fields = '__all__'

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
            raise serializers.ValidationError('Необходимо указать image или image_path')
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
