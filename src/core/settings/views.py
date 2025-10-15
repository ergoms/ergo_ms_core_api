import mimetypes
import os
from rest_framework.response import Response
from rest_framework import viewsets, status
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated

from .models import Category
from .serializers import CategorySerializer
from .models import UserAvatar
from .serializers import UserAvatarSerializer
from rest_framework.permissions import IsAuthenticated
from django.http import FileResponse
from rest_framework.views import APIView
from django.conf import settings
from django.forms.models import model_to_dict
from .audit import log_audit
from .models import AuditLog
from .serializers import AuditLogSerializer
from rest_framework.viewsets import ReadOnlyModelViewSet
from rest_framework.permissions import IsAdminUser

from rest_framework.parsers import MultiPartParser, FormParser, JSONParser

from .models import *
from .serializers import *

from .models import AuditLog
from .serializers import AuditLogSerializer

class GeneralSettingsViewSet(viewsets.ModelViewSet):
    queryset = GeneralSettings.objects.all()
    serializer_class = GeneralSettingsSerializer

    @action(detail=False, methods=['get'], url_path='last')
    def get_last_settings(self, request):
        last_settings = self.queryset.order_by('-id').first()
        if last_settings:
            serializer = self.get_serializer(last_settings)
            return Response(serializer.data)
        return Response({'detail': 'Нет ни одной записи настроек.'}, status=status.HTTP_404_NOT_FOUND)
    
    def perform_update(self, serializer):
        old_obj = self.get_object()
        old_data = model_to_dict(old_obj)

        new_obj = serializer.save()
        new_data = model_to_dict(new_obj)

        diff = {
            field: [old_data[field], new_data[field]]
            for field in old_data
            if old_data[field] != new_data[field]
        }

        if diff:
            log_audit(self.request, new_obj, 'UPDATE', diff)

    def perform_destroy(self, instance):
        log_audit(self.request, instance, 'DELETE')

        instance.delete()

class AppearanceSettingsViewSet(viewsets.ModelViewSet):
    queryset = AppearanceSettings.objects.all()
    serializer_class = AppearanceSettingsSerializer

class SecuritySettingsViewSet(viewsets.ModelViewSet):
    queryset = SecuritySettings.objects.all()
    serializer_class = SecuritySettingsSerializer

class MediaSettingsViewSet(viewsets.ModelViewSet):
    queryset = MediaSettings.objects.all()
    serializer_class = MediaSettingsSerializer

class PermalinkSettingsViewSet(viewsets.ModelViewSet):
    queryset = PermalinkSettings.objects.all()
    serializer_class = PermalinkSettingsSerializer

class EmailSettingsViewSet(viewsets.ModelViewSet):
    queryset = EmailSettings.objects.all()
    serializer_class = EmailSettingsSerializer
class FileViewSet(viewsets.ModelViewSet):
    queryset = UploadedFile.objects.all()
    serializer_class = UploadedFileSerializer
    parser_classes = [MultiPartParser, FormParser, JSONParser]

    def create(self, request, *args, **kwargs):
        file = request.FILES.get('file')
        alt_name = request.data.get('alt_name', '')

        if not file:
            return Response({'error': 'Файл не передан'}, status=status.HTTP_400_BAD_REQUEST)

        instance = UploadedFile.objects.create(file=file, alt_name=alt_name)
        return Response(UploadedFileSerializer(instance).data, status=status.HTTP_201_CREATED)
    
    def destroy(self, request, *args, **kwargs):
        instance = self.get_object()
        instance.file.delete(save=False)
        self.perform_destroy(instance)
        return Response(status=status.HTTP_204_NO_CONTENT)
    def download(self, request, pk=None):
        """Позволяет скачать файл по id всем, кто знает ссылку."""
        file_obj = self.get_object()
        file_handle = file_obj.file.open('rb')
        filename = file_obj.alt_name or file_obj.file.name.split('/')[-1]
        response = FileResponse(file_handle, as_attachment=True, filename=filename)
        return response
class FileDownloadByNameView(APIView):
    def get(self, request, filename, *args, **kwargs):
        if '..' in filename or filename.startswith('/'):
            return Response({'error': 'Invalid filename'}, status=status.HTTP_400_BAD_REQUEST)

        upload_root = os.path.abspath(os.path.join(settings.MEDIA_ROOT, 'uploads'))
        file_path   = os.path.abspath(os.path.join(upload_root, filename))

        if not file_path.startswith(upload_root):
            return Response({'error': 'Invalid path'}, status=status.HTTP_400_BAD_REQUEST)
        if not os.path.exists(file_path):
            return Response({'error': 'File not found'}, status=status.HTTP_404_NOT_FOUND)

        mime, _ = mimetypes.guess_type(file_path)
        resp = FileResponse(open(file_path, 'rb'),
                            as_attachment=False,
                            filename=filename,
                            content_type=mime or 'application/octet-stream')
        resp['Content-Disposition'] = f'inline; filename="{filename}"'
        return resp

class CategoryViewSet(viewsets.ModelViewSet):
    queryset = Category.objects.all()
    serializer_class = CategorySerializer
class TagViewSet(viewsets.ModelViewSet):
    queryset = Tag.objects.all()
    serializer_class = TagSerializer

class UserAvatarViewSet(viewsets.ModelViewSet):
    queryset = UserAvatar.objects.all()
    serializer_class = UserAvatarSerializer
    permission_classes = [IsAuthenticated]
    
    def get_queryset(self):
        # Обходим проблему с генерацией swagger схемы для анонимных пользователей
        if getattr(self, 'swagger_fake_view', False):
            return UserAvatar.objects.none()
        
        # Проверяем, что пользователь аутентифицирован
        if not self.request.user.is_authenticated:
            return UserAvatar.objects.none()
            
        return UserAvatar.objects.filter(user=self.request.user)
    
    def perform_create(self, serializer):
        if self.request.user.is_authenticated:
            UserAvatar.objects.filter(user=self.request.user).delete()
            serializer.save(user=self.request.user)

class AuditLogViewSet(ReadOnlyModelViewSet):
    queryset = AuditLog.objects.all()
    serializer_class = AuditLogSerializer
    permission_classes = [IsAdminUser]
    filterset_fields = ['content_type__model', 'object_id', 'action']
    ordering = ['-timestamp']
        