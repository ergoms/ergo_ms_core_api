from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from src.core.utils.media_signing import get_upload_info


class MediaUploadTokenView(APIView):
    """
    Генерирует upload-токен для загрузки файла в media_api.

    POST /api/utils/media/upload-token/
    Body: {target_dir, max_size?, allowed_types?}
    Response: {upload_url, token}
    """
    permission_classes = [IsAuthenticated]

    def post(self, request):
        target_dir = request.data.get('target_dir', '')
        max_size = request.data.get('max_size')
        allowed_types = request.data.get('allowed_types')

        if max_size is not None:
            max_size = int(max_size)

        upload_info = get_upload_info(
            user_id=request.user.id,
            target_dir=target_dir,
            max_size=max_size,
            allowed_types=allowed_types,
        )
        return Response(upload_info)
