"""
Сервис регистрации и приглашений пользователей.
"""

import secrets
from datetime import timedelta
from typing import Optional

from django.conf import settings
from django.contrib.auth.models import User
from django.db import transaction
from django.utils import timezone

from src.core.cms.adp.models import RegistrationInvitation
from src.core.utils.methods import send_registration_invitation_email


class RegistrationService:
    MODE_OPEN = 'open'
    MODE_INVITATION = 'invitation'
    MODE_CLOSED = 'closed'

    @staticmethod
    def get_mode() -> str:
        mode = getattr(settings, 'REGISTRATION_MODE', RegistrationService.MODE_OPEN)
        if mode not in (RegistrationService.MODE_OPEN, RegistrationService.MODE_INVITATION, RegistrationService.MODE_CLOSED):
            return RegistrationService.MODE_OPEN
        return mode

    @staticmethod
    def is_registration_enabled() -> bool:
        return RegistrationService.get_mode() != RegistrationService.MODE_CLOSED

    @staticmethod
    def requires_invitation() -> bool:
        return RegistrationService.get_mode() == RegistrationService.MODE_INVITATION

    @staticmethod
    def get_invitation_ttl_days() -> int:
        ttl = getattr(settings, 'REGISTRATION_INVITATION_TTL_DAYS', 7)
        return max(1, int(ttl))

    @staticmethod
    def get_public_settings() -> dict:
        mode = RegistrationService.get_mode()
        return {
            'mode': mode,
            'registration_enabled': mode != RegistrationService.MODE_CLOSED,
            'invitation_required': mode == RegistrationService.MODE_INVITATION,
        }

    @staticmethod
    def build_invitation_url(token: str) -> str:
        base_url = getattr(settings, 'FRONTEND_BASE_URL', 'http://localhost:8001').rstrip('/')
        return f'{base_url}/register?invite={token}'

    @staticmethod
    def generate_token() -> str:
        return secrets.token_urlsafe(32)

    @staticmethod
    def get_invitation_status(invitation: RegistrationInvitation) -> str:
        if invitation.is_revoked:
            return 'revoked'
        if invitation.used_at:
            return 'used'
        if invitation.expires_at <= timezone.now():
            return 'expired'
        return 'pending'

    @staticmethod
    def is_invitation_valid(invitation: Optional[RegistrationInvitation]) -> bool:
        if not invitation:
            return False
        return RegistrationService.get_invitation_status(invitation) == 'pending'

    @staticmethod
    def get_invitation_by_token(token: str) -> Optional[RegistrationInvitation]:
        if not token:
            return None
        try:
            return RegistrationInvitation.objects.select_related('invited_by').get(token=token.strip())
        except RegistrationInvitation.DoesNotExist:
            return None

    @staticmethod
    def get_valid_invitation(token: str) -> Optional[RegistrationInvitation]:
        invitation = RegistrationService.get_invitation_by_token(token)
        if RegistrationService.is_invitation_valid(invitation):
            return invitation
        return None

    @staticmethod
    def has_active_invitation_for_email(email: str) -> bool:
        normalized_email = (email or '').strip().lower()
        if not normalized_email:
            return False
        now = timezone.now()
        return RegistrationInvitation.objects.filter(
            email__iexact=normalized_email,
            is_revoked=False,
            used_at__isnull=True,
            expires_at__gt=now,
        ).exists()

    @staticmethod
    @transaction.atomic
    def create_invitation(*, email: str, invited_by: User, note: str = '', send_email: bool = False) -> tuple:
        normalized_email = email.strip().lower()
        if RegistrationService.has_active_invitation_for_email(normalized_email):
            return None, 'Для этого email уже есть активное приглашение'

        expires_at = timezone.now() + timedelta(days=RegistrationService.get_invitation_ttl_days())
        invitation = RegistrationInvitation.objects.create(
            email=normalized_email,
            token=RegistrationService.generate_token(),
            invited_by=invited_by,
            expires_at=expires_at,
            note=(note or '').strip(),
        )

        email_error = None
        if send_email:
            success, email_error = RegistrationService.send_invitation_email(invitation)
            if not success:
                return invitation, email_error

        return invitation, None

    @staticmethod
    def send_invitation_email(invitation: RegistrationInvitation) -> tuple:
        if not RegistrationService.is_invitation_valid(invitation):
            return False, 'Приглашение недействительно или истекло'

        invite_url = RegistrationService.build_invitation_url(invitation.token)
        ttl_days = RegistrationService.get_invitation_ttl_days()

        return send_registration_invitation_email(
            email=invitation.email,
            invite_url=invite_url,
            ttl_days=ttl_days,
        )

    @staticmethod
    @transaction.atomic
    def mark_invitation_used(invitation: RegistrationInvitation, user: User):
        invitation.used_at = timezone.now()
        invitation.used_by = user
        invitation.save(update_fields=['used_at', 'used_by'])

    @staticmethod
    def revoke_invitation(invitation: RegistrationInvitation) -> tuple:
        if invitation.used_at:
            return False, 'Нельзя отозвать уже использованное приглашение'
        if invitation.is_revoked:
            return False, 'Приглашение уже отозвано'

        invitation.is_revoked = True
        invitation.save(update_fields=['is_revoked'])
        return True, None
