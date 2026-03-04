from django.contrib.auth import get_user_model
from django.contrib.contenttypes.models import ContentType
from rest_framework import serializers

from .models import Message, MessageAttachment

User = get_user_model()

MAX_ATTACHMENT_SIZE_MB = 25
MAX_ATTACHMENT_SIZE_BYTES = MAX_ATTACHMENT_SIZE_MB * 1024 * 1024


class MessageAttachmentSerializer(serializers.ModelSerializer):
    file = serializers.FileField(write_only=True)
    file_url = serializers.SerializerMethodField()

    class Meta:
        model = MessageAttachment
        fields = (
            'id',
            'message',
            'file',
            'file_url',
            'original_filename',
            'file_size',
            'mime_type',
            'created_at',
        )
        read_only_fields = ('id', 'original_filename', 'file_size', 'mime_type', 'file_url', 'created_at')

    def validate_file(self, value):
        if value.size > MAX_ATTACHMENT_SIZE_BYTES:
            raise serializers.ValidationError(
                f'Размер файла не должен превышать {MAX_ATTACHMENT_SIZE_MB} МБ'
            )
        return value

    def get_file_url(self, obj):
        request = self.context.get('request')
        if request and obj.file:
            try:
                return request.build_absolute_uri(obj.file.url)
            except Exception:
                return obj.file.url if obj.file else None
        return obj.file.url if obj.file else None

    def create(self, validated_data):
        uploaded_file = validated_data.get('file')
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
    object_id = serializers.IntegerField(required=False)
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
        try:
            ContentType.objects.get(model=value)
        except ContentType.DoesNotExist:
            raise serializers.ValidationError(f'Тип контента "{value}" не найден')
        return value

    def validate(self, attrs):
        if not self.instance and not attrs.get('content_type_name'):
            raise serializers.ValidationError({'content_type_name': 'Обязательное поле при создании.'})
        if not self.instance and attrs.get('object_id') is None:
            raise serializers.ValidationError({'object_id': 'Обязательное поле при создании.'})
        return attrs

    def get_author_data(self, obj):
        if not obj.author:
            return None
        user = obj.author
        full_name = user.get_full_name() if hasattr(user, 'get_full_name') else ''
        avatar_url = None
        request = self.context.get('request')
        if request:
            try:
                if hasattr(user, 'avatar') and user.avatar and user.avatar.image:
                    avatar_url = request.build_absolute_uri(user.avatar.image.url)
            except Exception:
                pass
        return {
            'id': user.id,
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
        ct = ContentType.objects.get(model=content_type_name)
        validated_data['content_type'] = ct
        return super().create(validated_data)
