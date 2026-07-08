from django.contrib.auth import get_user_model

User = get_user_model()
from rest_framework.serializers import (
    CharField,
    EmailField,
    ModelSerializer,
    SerializerMethodField,
    ValidationError,
)

from src.core.cms.adp.models import UserDevice, UserProfile
from src.core.cms.adp.services.registration import RegistrationService
from src.core.cms.adp.user_agent_utils import (
    format_device_location,
    get_device_type_display,
    parse_user_agent,
)


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
    Минимальный сериализатор пользователя для меню и session-bootstrap.
    Возвращает данные для бокового меню и карточки профиля:
    username, email, first_name, middle_name, full_name, initials_name, date_joined.
    Используется в эндпоинте /api/cms/adp/user-menu-data/ и session-bootstrap.
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
            'date_joined',
        ]
        read_only_fields = ['id', 'full_name', 'initials_name', 'date_joined']

    def get_full_name(self, obj):
        full_name = obj.get_full_name()
        return full_name if isinstance(full_name, str) else str(full_name or '')

    def get_initials_name(self, obj):
        initials = obj.get_initials_name()
        return initials if isinstance(initials, str) else str(initials or '')


class CMSUserBasicSerializer(ModelSerializer):
    """
    Легковесный сериализатор пользователя без профиля.
    Используется для быстрой проверки токена и базовой инициализации.
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
    """Полный сериализатор пользователя с профилем."""
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
