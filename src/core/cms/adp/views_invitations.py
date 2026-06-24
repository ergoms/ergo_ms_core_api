"""
API для приглашений на регистрацию и публичных настроек регистрации.
"""

from django.db.models import Q
from drf_yasg import openapi
from drf_yasg.utils import swagger_auto_schema
from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from src.core.utils.base.base_views import BaseAPIView, BaseAPIViewAuthMixin
from src.core.cms.adp.models import RegistrationInvitation
from src.core.cms.adp.serializers import (
    RegistrationInvitationSerializer,
    CreateRegistrationInvitationSerializer,
    BulkCreateRegistrationInvitationsSerializer,
    BulkSendRegistrationInvitationsSerializer,
    ValidateInvitationSerializer,
)
from src.core.cms.adp.services.registration import RegistrationService
from src.core.cms.adp.views_roles import _require_global_admin


def _serialize_invitation(invitation):
    return RegistrationInvitationSerializer(invitation).data


def _parse_pagination(request, default_page_size=12):
    try:
        page = max(1, int(request.query_params.get('page', 1)))
    except (TypeError, ValueError):
        page = 1
    try:
        page_size = min(100, max(1, int(request.query_params.get('page_size', default_page_size))))
    except (TypeError, ValueError):
        page_size = default_page_size
    search = (request.query_params.get('search') or '').strip()
    return page, page_size, search


class RegistrationSettingsView(BaseAPIView):
    """Публичные настройки режима регистрации."""

    @swagger_auto_schema(
        operation_description='Получить настройки режима регистрации',
        responses={200: openapi.Response(description='Настройки регистрации')},
    )
    def get(self, request):
        return Response(RegistrationService.get_public_settings())


class ValidateInvitationView(BaseAPIView):
    """Проверка токена приглашения (публичный endpoint)."""

    @swagger_auto_schema(
        operation_description='Проверить токен приглашения',
        manual_parameters=[
            openapi.Parameter(
                'token',
                openapi.IN_QUERY,
                description='Токен приглашения',
                type=openapi.TYPE_STRING,
                required=True,
            ),
        ],
        responses={200: ValidateInvitationSerializer()},
    )
    def get(self, request):
        token = (request.query_params.get('token') or '').strip()
        invitation = RegistrationService.get_invitation_by_token(token)

        if not invitation:
            return Response({
                'valid': False,
                'email': None,
                'expires_at': None,
                'status': None,
            })

        invitation_status = RegistrationService.get_invitation_status(invitation)
        return Response({
            'valid': invitation_status == 'pending',
            'email': invitation.email,
            'expires_at': invitation.expires_at,
            'status': invitation_status,
        })


class RegistrationInvitationListView(BaseAPIViewAuthMixin, BaseAPIView):
    """Список и создание приглашений (только глобальные администраторы)."""

    permission_classes = [IsAuthenticated]

    @swagger_auto_schema(
        operation_description='Получить список приглашений',
        responses={200: RegistrationInvitationSerializer(many=True)},
    )
    def get(self, request):
        forbidden = _require_global_admin(request)
        if forbidden:
            return forbidden

        page, page_size, search = _parse_pagination(request)
        queryset = RegistrationInvitation.objects.select_related('invited_by').order_by('-created_at')

        if search:
            queryset = queryset.filter(
                Q(email__icontains=search)
                | Q(note__icontains=search)
                | Q(invited_by__username__icontains=search)
            )

        total = queryset.count()
        offset = (page - 1) * page_size
        invitations = list(queryset[offset:offset + page_size])
        serializer = RegistrationInvitationSerializer(invitations, many=True)

        return Response({
            'invitations': serializer.data,
            'total': total,
            'page': page,
            'page_size': page_size,
            'registration_mode': RegistrationService.get_mode(),
        })

    @swagger_auto_schema(
        operation_description='Создать приглашение на регистрацию',
        request_body=CreateRegistrationInvitationSerializer,
        responses={201: RegistrationInvitationSerializer()},
    )
    def post(self, request):
        forbidden = _require_global_admin(request)
        if forbidden:
            return forbidden

        if RegistrationService.get_mode() != RegistrationService.MODE_INVITATION:
            return Response(
                {'error': 'Режим регистрации по приглашениям не включён (API_REGISTRATION_MODE=invitation).'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        serializer = CreateRegistrationInvitationSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        invitation, error = RegistrationService.create_invitation(
            email=serializer.validated_data['email'],
            invited_by=request.user,
            note=serializer.validated_data.get('note', ''),
            send_email=serializer.validated_data.get('send_email', False),
        )
        if error and not invitation:
            return Response({'error': error}, status=status.HTTP_400_BAD_REQUEST)

        response_data = _serialize_invitation(invitation)
        if error:
            response_data['email_warning'] = error

        return Response(response_data, status=status.HTTP_201_CREATED)


class RegistrationInvitationDetailView(BaseAPIViewAuthMixin, BaseAPIView):
    permission_classes = [IsAuthenticated]

    def _get_invitation(self, invitation_id):
        try:
            return RegistrationInvitation.objects.select_related('invited_by').get(pk=invitation_id)
        except RegistrationInvitation.DoesNotExist:
            return None

    @swagger_auto_schema(
        operation_description='Отозвать приглашение',
        responses={204: 'Приглашение отозвано'},
    )
    def delete(self, request, invitation_id):
        forbidden = _require_global_admin(request)
        if forbidden:
            return forbidden

        invitation = self._get_invitation(invitation_id)
        if not invitation:
            return Response({'error': 'Приглашение не найдено'}, status=status.HTTP_404_NOT_FOUND)

        success, error = RegistrationService.revoke_invitation(invitation)
        if not success:
            return Response({'error': error}, status=status.HTTP_400_BAD_REQUEST)

        return Response(status=status.HTTP_204_NO_CONTENT)


class RegistrationInvitationResendView(BaseAPIViewAuthMixin, BaseAPIView):
    permission_classes = [IsAuthenticated]

    @swagger_auto_schema(
        operation_description='Повторно отправить email с приглашением',
        responses={200: RegistrationInvitationSerializer()},
    )
    def post(self, request, invitation_id):
        forbidden = _require_global_admin(request)
        if forbidden:
            return forbidden

        try:
            invitation = RegistrationInvitation.objects.select_related('invited_by').get(pk=invitation_id)
        except RegistrationInvitation.DoesNotExist:
            return Response({'error': 'Приглашение не найдено'}, status=status.HTTP_404_NOT_FOUND)

        success, error = RegistrationService.send_invitation_email(invitation)
        if not success:
            return Response({'error': error}, status=status.HTTP_400_BAD_REQUEST)

        return Response(_serialize_invitation(invitation))


class RegistrationInvitationBulkCreateView(BaseAPIViewAuthMixin, BaseAPIView):
    permission_classes = [IsAuthenticated]

    @swagger_auto_schema(
        operation_description='Массовое создание приглашений по списку email',
        request_body=BulkCreateRegistrationInvitationsSerializer,
    )
    def post(self, request):
        forbidden = _require_global_admin(request)
        if forbidden:
            return forbidden

        if RegistrationService.get_mode() != RegistrationService.MODE_INVITATION:
            return Response(
                {'error': 'Режим регистрации по приглашениям не включён (API_REGISTRATION_MODE=invitation).'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        serializer = BulkCreateRegistrationInvitationsSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        result = RegistrationService.bulk_create_invitations(
            emails=serializer.validated_data['emails'],
            invited_by=request.user,
            note=serializer.validated_data.get('note', ''),
            send_email=serializer.validated_data.get('send_email', False),
        )
        return Response(result, status=status.HTTP_201_CREATED)


class RegistrationInvitationBulkSendView(BaseAPIViewAuthMixin, BaseAPIView):
    permission_classes = [IsAuthenticated]

    @swagger_auto_schema(
        operation_description='Массовая отправка email с приглашениями',
        request_body=BulkSendRegistrationInvitationsSerializer,
    )
    def post(self, request):
        forbidden = _require_global_admin(request)
        if forbidden:
            return forbidden

        serializer = BulkSendRegistrationInvitationsSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        result = RegistrationService.bulk_send_invitation_emails(
            invitation_ids=serializer.validated_data['invitation_ids'],
        )
        return Response(result)
