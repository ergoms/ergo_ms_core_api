from drf_yasg import openapi
from drf_yasg.utils import swagger_auto_schema
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from src.core.cms.adp.serializers import UserPresenceBatchResponseSerializer
from src.core.cms.adp.services import presence as presence_service
from src.core.utils.base.base_views import BaseAPIView, BaseAPIViewAuthMixin


class UserPresenceBatchView(BaseAPIViewAuthMixin, BaseAPIView):
    """Batch-запрос онлайн-статуса пользователей для UI (аватарки, списки и т.д.)."""

    permission_classes = [IsAuthenticated]

    @swagger_auto_schema(
        operation_description='Получить онлайн-статус пользователей по списку ID.',
        manual_parameters=[
            openapi.Parameter(
                'user_ids',
                openapi.IN_QUERY,
                description='ID пользователей через запятую (максимум 100)',
                type=openapi.TYPE_STRING,
                required=True,
            ),
        ],
        responses={200: UserPresenceBatchResponseSerializer()},
    )
    def get(self, request):
        user_ids = presence_service.parse_user_ids_param(request.query_params.get('user_ids'))
        if not user_ids:
            return Response({'presence': {}})

        presence_map = presence_service.get_presence_map(user_ids)
        return Response({
            'presence': presence_service.serialize_presence_map(presence_map),
        })
