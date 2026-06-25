from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from src.core.utils.module_registry import get_disabled_modules


class DisabledModulesView(APIView):
    """Возвращает список отключённых модулей для клиента."""
    permission_classes = [IsAuthenticated]

    def get(self, request):
        return Response({'disabled_modules': sorted(get_disabled_modules())})
