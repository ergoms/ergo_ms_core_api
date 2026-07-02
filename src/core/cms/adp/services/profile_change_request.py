"""
Сервис заявок пользователей на изменение email и ФИО.
"""

from django.contrib.auth.models import User
from django.core.exceptions import ValidationError as DjangoValidationError
from django.core.validators import validate_email
from django.db import transaction
from django.utils import timezone

from src.core.cms.adp.models import UserProfileChangeRequest
from src.core.cms.adp.services.profile_settings import ProfileSettingsService
from src.core.cms.adp.services.registration import RegistrationService


class ProfileChangeRequestService:
    PENDING_EXISTS_MESSAGE = 'У вас уже есть заявка на рассмотрении.'
    NOT_ALLOWED_MESSAGE = 'Заявки на изменение данных недоступны: редактирование разрешено.'
    NO_CHANGES_MESSAGE = 'Новые данные совпадают с текущими.'
    ALREADY_REVIEWED_MESSAGE = 'Заявка уже обработана.'
    INVALID_EMAIL_MESSAGE = 'Укажите корректный email.'

    @staticmethod
    def is_request_flow_enabled() -> bool:
        return not ProfileSettingsService.is_self_fio_edit_enabled()

    @staticmethod
    def normalize_name_part(value) -> str:
        if value is None:
            return ''
        if isinstance(value, str):
            return value.strip()
        return str(value).strip()

    @staticmethod
    def normalize_email(value) -> str:
        if value is None:
            return ''
        if isinstance(value, str):
            return value.strip().lower()
        return str(value).strip().lower()

    @staticmethod
    def get_user_profile_data(user: User) -> dict[str, str]:
        return {
            'email': ProfileChangeRequestService.normalize_email(user.email),
            'first_name': ProfileChangeRequestService.normalize_name_part(user.first_name),
            'last_name': ProfileChangeRequestService.normalize_name_part(user.last_name),
            'middle_name': ProfileChangeRequestService.normalize_name_part(
                getattr(user, 'middle_name', ''),
            ),
        }

    @staticmethod
    def profile_data_differs(
        user: User,
        *,
        email: str,
        first_name: str,
        last_name: str,
        middle_name: str,
    ) -> bool:
        current = ProfileChangeRequestService.get_user_profile_data(user)
        requested = {
            'email': ProfileChangeRequestService.normalize_email(email),
            'first_name': ProfileChangeRequestService.normalize_name_part(first_name),
            'last_name': ProfileChangeRequestService.normalize_name_part(last_name),
            'middle_name': ProfileChangeRequestService.normalize_name_part(middle_name),
        }
        return current != requested

    @staticmethod
    def validate_requested_email(email: str, *, exclude_user_id: int | None = None) -> str:
        normalized = ProfileChangeRequestService.normalize_email(email)
        if not normalized:
            raise ValueError(ProfileChangeRequestService.INVALID_EMAIL_MESSAGE)
        try:
            validate_email(normalized)
        except DjangoValidationError as exc:
            raise ValueError(ProfileChangeRequestService.INVALID_EMAIL_MESSAGE) from exc

        uniqueness_error = RegistrationService.validate_email_uniqueness(
            normalized,
            exclude_user_id=exclude_user_id,
        )
        if uniqueness_error:
            raise ValueError(uniqueness_error)
        return normalized

    @staticmethod
    def has_pending_request(user: User) -> bool:
        return UserProfileChangeRequest.objects.filter(
            user=user,
            status=UserProfileChangeRequest.STATUS_PENDING,
        ).exists()

    @staticmethod
    def create_request(
        user: User,
        *,
        email: str,
        first_name: str,
        last_name: str,
        middle_name: str,
        comment: str = '',
    ):
        if not ProfileChangeRequestService.is_request_flow_enabled():
            raise ValueError(ProfileChangeRequestService.NOT_ALLOWED_MESSAGE)

        normalized_email = ProfileChangeRequestService.validate_requested_email(
            email,
            exclude_user_id=user.pk,
        )
        normalized = {
            'first_name': ProfileChangeRequestService.normalize_name_part(first_name),
            'last_name': ProfileChangeRequestService.normalize_name_part(last_name),
            'middle_name': ProfileChangeRequestService.normalize_name_part(middle_name),
            'comment': (comment or '').strip(),
        }

        if not normalized['first_name'] and not normalized['last_name']:
            raise ValueError('Укажите имя или фамилию.')

        if not ProfileChangeRequestService.profile_data_differs(
            user,
            email=normalized_email,
            first_name=normalized['first_name'],
            last_name=normalized['last_name'],
            middle_name=normalized['middle_name'],
        ):
            raise ValueError(ProfileChangeRequestService.NO_CHANGES_MESSAGE)

        if ProfileChangeRequestService.has_pending_request(user):
            raise ValueError(ProfileChangeRequestService.PENDING_EXISTS_MESSAGE)

        return UserProfileChangeRequest.objects.create(
            user=user,
            email=normalized_email,
            first_name=normalized['first_name'],
            last_name=normalized['last_name'],
            middle_name=normalized['middle_name'],
            comment=normalized['comment'],
        )

    @staticmethod
    @transaction.atomic
    def approve_request(request_obj: UserProfileChangeRequest, reviewer: User):
        if request_obj.status != UserProfileChangeRequest.STATUS_PENDING:
            raise ValueError(ProfileChangeRequestService.ALREADY_REVIEWED_MESSAGE)

        user = User.objects.select_for_update().get(pk=request_obj.user_id)
        normalized_email = ProfileChangeRequestService.validate_requested_email(
            request_obj.email,
            exclude_user_id=user.pk,
        )
        user.email = normalized_email
        user.first_name = request_obj.first_name
        user.last_name = request_obj.last_name
        user.middle_name = request_obj.middle_name
        user.save(update_fields=['email', 'first_name', 'last_name', 'middle_name'])

        request_obj.status = UserProfileChangeRequest.STATUS_APPROVED
        request_obj.reviewed_by = reviewer
        request_obj.reviewed_at = timezone.now()
        request_obj.save(update_fields=['status', 'reviewed_by', 'reviewed_at'])
        return request_obj

    @staticmethod
    @transaction.atomic
    def reject_request(
        request_obj: UserProfileChangeRequest,
        reviewer: User,
        admin_comment: str = '',
    ):
        if request_obj.status != UserProfileChangeRequest.STATUS_PENDING:
            raise ValueError(ProfileChangeRequestService.ALREADY_REVIEWED_MESSAGE)

        request_obj.status = UserProfileChangeRequest.STATUS_REJECTED
        request_obj.admin_comment = (admin_comment or '').strip()
        request_obj.reviewed_by = reviewer
        request_obj.reviewed_at = timezone.now()
        request_obj.save(update_fields=['status', 'admin_comment', 'reviewed_by', 'reviewed_at'])
        return request_obj
