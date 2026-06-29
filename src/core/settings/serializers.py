from django.contrib.contenttypes.models import ContentType

from rest_framework import serializers

from .models import Category
from .models import Tag
from .models import UserAvatar
from src.core.utils.mixins import validate_media_path
from .models import (
    GeneralSettings, AppearanceSettings, Theme,
    SecuritySettings, MediaSettings, PermalinkSettings, EmailSettings, AuditLog
)

class GeneralSettingsSerializer(serializers.ModelSerializer):
    class Meta:
        model = GeneralSettings
        fields = '__all__'

class GeneralSettingsReadSerializer(serializers.ModelSerializer):
    """Сериализатор для чтения настроек (без лишних полей)"""
    class Meta:
        model = GeneralSettings
        fields = [
            'id',
            'site_name',
            'site_tagline',
            'site_url',
            'admin_email',
            'homepage_type',
            'posts_per_page',
            'discourage_search_engines',
            'privacy_policy',
        ]
        read_only_fields = fields

class GeneralSettingsSiteNameSerializer(serializers.ModelSerializer):
    """Сериализатор только для названия сайта (для меню)"""
    class Meta:
        model = GeneralSettings
        fields = ['site_name']
        read_only_fields = fields

class AppearanceSettingsSerializer(serializers.ModelSerializer):
    class Meta:
        model = AppearanceSettings
        fields = '__all__'


class ThemeSerializer(serializers.ModelSerializer):
    """Сериализатор для тем оформления"""
    
    class Meta:
        model = Theme
        fields = [
            'id', 'name', 'description', 'author', 'base_theme',
            'is_active', 'is_default', 'is_system',
            'colors', 'bootstrap_colors',
            'created_at', 'updated_at'
        ]
        read_only_fields = ['created_at', 'updated_at', 'is_system']
        # Уникальное имя схемы для Swagger, чтобы не конфликтовать с LmsThemeSerializer
        ref_name = 'CoreThemeSerializer'
    
    def validate(self, data):
        # Нельзя редактировать системные темы
        if self.instance and self.instance.is_system:
            # Можно только активировать/деактивировать
            allowed_fields = {'is_active', 'is_default'}
            changed_fields = set(data.keys()) - allowed_fields
            if changed_fields:
                raise serializers.ValidationError(
                    "Нельзя редактировать системные темы. "
                    "Создайте копию для редактирования."
                )
        return data


class ThemeExportSerializer(serializers.Serializer):
    """Сериализатор для экспорта темы"""
    name = serializers.CharField()
    description = serializers.CharField(allow_blank=True, required=False)
    author = serializers.CharField(allow_blank=True, required=False)
    base_theme = serializers.ChoiceField(choices=['light', 'dark'])
    colors = serializers.JSONField()
    bootstrap_colors = serializers.JSONField(required=False, default=dict)
    version = serializers.CharField(default='1.0')
    exported_at = serializers.DateTimeField(read_only=True)

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
class CategorySerializer(serializers.ModelSerializer):
    class Meta:
        model = Category
        fields = ['id', 'name', 'parent', 'slug']
        read_only_fields = ['slug']
        ref_name = 'SettingsCategory'
    def to_representation(self, instance):
        ret = super().to_representation(instance)
        ret['slug'] = instance.slug
        return ret
class TagSerializer(serializers.ModelSerializer):
    class Meta:
        model = Tag
        fields = ['id', 'name', 'category']
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

class AuditLogSerializer(serializers.ModelSerializer):
    content_type = serializers.SlugRelatedField(
        read_only=True,
        slug_field='model'
    )
    user = serializers.CharField(
        source='user.username',
        default=None,
        read_only=True
    )
    action = serializers.SerializerMethodField()

    class Meta:
        model = AuditLog
        fields = [
            'id',
            'content_type',
            'object_id',
            'action',
            'changes',
            'user',
            'timestamp',
        ]
        read_only_fields = fields

    def get_action(self, obj):
        return obj.get_action_display()