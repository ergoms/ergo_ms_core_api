from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from src.core.cms.adp.services.permissions import PermissionService
from src.core.utils.media_signing import get_upload_info


class MediaUploadTokenView(APIView):
    """
    Генерирует upload-токен для загрузки файла в media_api.

    POST /api/utils/media/upload-token/
    Body: {target_dir, max_size?, allowed_types?}
    Response: {upload_url, token}

    Параметры проверяются на сервере (см. media_upload_validation).
    Класс квоты частоты: admin для глобального администратора, иначе user.
    """
    permission_classes = [IsAuthenticated]

    def post(self, request):
        target_dir = request.data.get('target_dir', '')
        max_size = request.data.get('max_size')
        allowed_types = request.data.get('allowed_types')
        quota = 'admin' if PermissionService.is_admin(request.user) else 'user'

        upload_info = get_upload_info(
            user_id=request.user.id,
            target_dir=target_dir,
            max_size=max_size,
            allowed_types=allowed_types,
            quota=quota,
        )
        return Response(upload_info)
