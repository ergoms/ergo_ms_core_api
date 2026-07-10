from drf_yasg import openapi
from drf_yasg.utils import swagger_auto_schema
from rest_framework.response import Response

from src.core.utils.base.base_views import BaseAPIView
from src.core.utils.maintenance import is_maintenance_enabled, MAINTENANCE_DETAIL


class MaintenanceStatusView(BaseAPIView):
    @swagger_auto_schema(
        operation_description='Статус режима технических works (только чтение).',
        responses={200: openapi.Response('Maintenance status')},
    )
    def get(self, request):
        enabled = is_maintenance_enabled()
        payload = {'maintenance': enabled}
        if enabled:
            payload['detail'] = MAINTENANCE_DETAIL
        return Response(payload)
