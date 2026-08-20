from django.contrib.auth import get_user_model
from django.utils.translation import gettext as _
from rest_framework import serializers

from src.core.utils.mixins import validate_media_path

from .models import Message, MessageAttachment
from .utils import get_content_type

User = get_user_model()

MAX_ATTACHMENT_SIZE_MB = 25
MAX_ATTACHMENT_SIZE_BYTES = MAX_ATTACHMENT_SIZE_MB * 1024 * 1024


class MessengerObjectIdField(serializers.Field):
    """pk или public_id снаружи; в БД хранится integer pk."""

    def to_internal_value(self, data):
        if isinstance(data, bool) or data in (None, ''):
            raise serializers.ValidationError(_('Некорректный идентификатор.'))
        return str(data).strip()

    def to_representation(self, value):
        return value


class MessageAttachmentSerializer(serializers.ModelSerializer):
    file = serializers.FileField(write_only=True, required=False)
    file_path = serializers.CharField(write_only=True, required=False)
    file_url = serializers.SerializerMethodField()

    class Meta:
        model = MessageAttachment
        fields = (
            'id',
            'message',
            'file',
            'file_path',
            'file_url',
            'original_filename',
            'file_size',
            'mime_type',
            'created_at',
        )
        read_only_fields = ('id', 'original_filename', 'file_size', 'mime_type', 'file_url', 'created_at')

    def validate_file_path(self, value):
        if value:
            return validate_media_path(value, 'file')
        return value

    def validate(self, attrs):
        if not attrs.get('file') and not attrs.get('file_path'):
            raise serializers.ValidationError(_('Необходим file или file_path'))
        return attrs

    def validate_file(self, value):
        if value and value.size > MAX_ATTACHMENT_SIZE_BYTES:
            raise serializers.ValidationError(
                _('Размер файла не должен превышать %(count)d МБ')
                % {'count': MAX_ATTACHMENT_SIZE_MB}
            )
        return value

    def get_file_url(self, obj):
        if obj.file:
            try:
                return obj.file.url
            except Exception:
                return None
        return None

    def create(self, validated_data):
        file_path = validated_data.pop('file_path', None)
        uploaded_file = validated_data.get('file')

        if file_path:
            import os
            from django.core.files.storage import default_storage
            validated_data.pop('file', None)
            validated_data['original_filename'] = os.path.basename(file_path)
            validated_data['file_size'] = default_storage.size(file_path) if default_storage.exists(file_path) else 0
            validated_data['mime_type'] = ''
            instance = super().create(validated_data)
            instance.file.name = file_path
            instance.save()
            return instance

        validated_data['original_filename'] = uploaded_file.name
        validated_data['file_size'] = uploaded_file.size or 0
        validated_data['mime_type'] = getattr(uploaded_file, 'content_type', '') or ''
        return super().create(validated_data)


class AuthorSerializer(serializers.Serializer):
    id = serializers.IntegerField()
    username = serializers.CharField()
    full_name = serializers.CharField()
    avatar_url = serializers.CharField(allow_null=True)


class ReplyToSerializer(serializers.ModelSerializer):
    author_data = serializers.SerializerMethodField()
    text_preview = serializers.SerializerMethodField()

    class Meta:
        model = Message
        fields = ('id', 'text_preview', 'author_data')

    def get_text_preview(self, obj):
        t = (obj.text or '').strip()
        if not t:
            if obj.attachments.exists():
                return 'Вложение'
            return ''
        return t[:100] + ('...' if len(t) > 100 else '')

    def get_author_data(self, obj):
        if not obj.author:
            return None
        user = obj.author
        full_name = user.get_full_name() if hasattr(user, 'get_full_name') else ''
        return {
            'id': user.id,
            'username': getattr(user, 'username', ''),
            'full_name': full_name or getattr(user, 'username', ''),
        }


class MessageSerializer(serializers.ModelSerializer):
    author_data = serializers.SerializerMethodField()
    attachments = MessageAttachmentSerializer(many=True, read_only=True)
    content_type_name = serializers.CharField(write_only=True, required=False)
    object_id = MessengerObjectIdField(required=False)
    reply_to = serializers.PrimaryKeyRelatedField(
        queryset=Message.objects.all(), required=False, allow_null=True,
    )
    reply_to_data = serializers.SerializerMethodField()

    class Meta:
        model = Message
        fields = (
            'id',
            'content_type_name',
            'object_id',
            'author',
            'author_data',
            'text',
            'message_type',
            'is_edited',
            'reply_to',
            'reply_to_data',
            'attachments',
            'created_at',
            'updated_at',
        )
        read_only_fields = ('id', 'author', 'author_data', 'is_edited', 'reply_to_data', 'attachments', 'created_at', 'updated_at')

    def validate_content_type_name(self, value):
        get_content_type(value)
        return value

    def validate(self, attrs):
        if not self.instance and not attrs.get('content_type_name'):
            raise serializers.ValidationError({'content_type_name': 'Обязательное поле при создании.'})
        if not self.instance and attrs.get('object_id') in (None, ''):
            raise serializers.ValidationError({'object_id': 'Обязательное поле при создании.'})
        if not self.instance:
            from src.core.messenger.access import resolve_messenger_object_pk

            object_pk = resolve_messenger_object_pk(
                attrs.get('content_type_name'),
                attrs.get('object_id'),
            )
            if object_pk is None:
                raise serializers.ValidationError({'object_id': _('Объект не найден.')})
            attrs['object_id'] = object_pk
        return attrs

    def get_author_data(self, obj):
        if not obj.author:
            return None
        user = obj.author
        full_name = user.get_full_name() if hasattr(user, 'get_full_name') else ''
        avatar_url = None
        request = self.context.get('request')
        try:
            if hasattr(user, 'avatar') and user.avatar and user.avatar.image:
                avatar_url = user.avatar.image.url
        except Exception:
            pass
        return {
            'id': user.id,
            'public_id': str(user.public_id) if getattr(user, 'public_id', None) else None,
            'username': getattr(user, 'username', ''),
            'full_name': full_name or getattr(user, 'username', ''),
            'avatar_url': avatar_url,
        }

    def get_reply_to_data(self, obj):
        if not obj.reply_to_id:
            return None
        return ReplyToSerializer(obj.reply_to).data

    def create(self, validated_data):
        content_type_name = validated_data.pop('content_type_name')
        ct = get_content_type(content_type_name)
        validated_data['content_type'] = ct
        return super().create(validated_data)
