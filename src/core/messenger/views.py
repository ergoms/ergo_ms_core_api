import logging

from asgiref.sync import async_to_sync
from channels.layers import get_channel_layer
from django.contrib.contenttypes.models import ContentType
from rest_framework import permissions, viewsets
from rest_framework.exceptions import PermissionDenied
from rest_framework.parsers import FormParser, MultiPartParser

from src.core.utils.mixins import SwaggerSafeMixin

from .models import Message, MessageAttachment
from .serializers import MessageAttachmentSerializer, MessageSerializer

logger = logging.getLogger('core.messenger')


class MessageViewSet(SwaggerSafeMixin, viewsets.ModelViewSet):
    serializer_class = MessageSerializer
    permission_classes = [permissions.IsAuthenticated]
    http_method_names = ['get', 'post', 'patch', 'delete', 'head', 'options']

    def get_queryset(self):
        if self.is_swagger_fake_view():
            return Message.objects.none()

        queryset = Message.objects.select_related(
            'author', 'content_type', 'reply_to', 'reply_to__author',
        ).prefetch_related('attachments')

        if self.kwargs.get('pk'):
            return queryset

        content_type_name = self.request.query_params.get('content_type')
        object_id = self.request.query_params.get('object_id')

        if content_type_name and object_id:
            try:
                ct = ContentType.objects.get(model=content_type_name)
                return queryset.filter(content_type=ct, object_id=object_id).order_by('created_at')
            except ContentType.DoesNotExist:
                return Message.objects.none()

        return Message.objects.none()

    def _check_author(self, instance):
        if instance.author != self.request.user:
            raise PermissionDenied('Вы можете изменять только свои сообщения.')

    def perform_create(self, serializer):
        message = serializer.save(author=self.request.user)
        self._broadcast(message, 'new_message')

    def perform_update(self, serializer):
        self._check_author(serializer.instance)
        message = serializer.save(is_edited=True)
        self._broadcast(message, 'message_edited')

    def perform_destroy(self, instance):
        self._check_author(instance)
        message_id = instance.id
        ct_name = instance.content_type.model if instance.content_type else ''
        object_id = instance.object_id
        instance.delete()
        self._broadcast_deleted(ct_name, object_id, message_id)

    def _broadcast(self, message, event_type):
        ct_name = message.content_type.model if message.content_type else ''
        group_name = f'messenger_{ct_name}_{message.object_id}'
        serialized = MessageSerializer(message, context={'request': self.request}).data
        try:
            channel_layer = get_channel_layer()
            async_to_sync(channel_layer.group_send)(
                group_name,
                {'type': event_type, 'message': serialized},
            )
        except Exception:
            logger.exception('Broadcast %s failed', event_type)

    def _broadcast_deleted(self, ct_name, object_id, message_id):
        group_name = f'messenger_{ct_name}_{object_id}'
        try:
            channel_layer = get_channel_layer()
            async_to_sync(channel_layer.group_send)(
                group_name,
                {'type': 'message_deleted', 'message_id': message_id},
            )
        except Exception:
            logger.exception('Broadcast message_deleted failed')


class MessageAttachmentViewSet(SwaggerSafeMixin, viewsets.ModelViewSet):
    serializer_class = MessageAttachmentSerializer
    permission_classes = [permissions.IsAuthenticated]
    parser_classes = (MultiPartParser, FormParser)
    http_method_names = ['get', 'post', 'delete', 'head', 'options']

    def get_queryset(self):
        if self.is_swagger_fake_view():
            return MessageAttachment.objects.none()

        queryset = MessageAttachment.objects.select_related('message').filter(
            message__author=self.request.user,
        )

        message_id = self.request.query_params.get('message')
        if message_id:
            queryset = queryset.filter(message_id=message_id)

        return queryset.order_by('created_at')
