from rest_framework.serializers import (
    BooleanField,
    CharField,
    ChoiceField,
    DateTimeField,
    IntegerField,
    ListField,
    Serializer,
    SerializerMethodField,
    ValidationError,
)

from src.core.cms.adp.services.registration import RegistrationService


class RegistrationInvitationSerializer(Serializer):
    id = IntegerField(read_only=True)
    email = CharField(read_only=True)
    token = CharField(read_only=True)
    invite_url = SerializerMethodField()
    status = SerializerMethodField()
    note = CharField(read_only=True)
    invited_by_id = IntegerField(read_only=True, allow_null=True)
    invited_by_name = SerializerMethodField()
    expires_at = DateTimeField(read_only=True)
    used_at = DateTimeField(read_only=True, allow_null=True)
    created_at = DateTimeField(read_only=True)

    def get_invite_url(self, obj):
        return RegistrationService.build_invitation_url(obj.token)

    def get_status(self, obj):
        return RegistrationService.get_invitation_status(obj)

    def get_invited_by_name(self, obj):
        if not obj.invited_by:
            return ''
        return obj.invited_by.get_full_name() or obj.invited_by.username


class CreateRegistrationInvitationSerializer(Serializer):
    email = CharField(required=True)
    note = CharField(required=False, allow_blank=True, default='')
    send_email = BooleanField(required=False, default=False)

    def validate_email(self, value):
        normalized = value.strip().lower()
        error = RegistrationService.validate_email_for_invitation(normalized)
        if error:
            raise ValidationError(error)
        return normalized


class BulkCreateRegistrationInvitationsSerializer(Serializer):
    emails = ListField(child=CharField(), allow_empty=False, max_length=500)
    note = CharField(required=False, allow_blank=True, default='')
    send_email = BooleanField(required=False, default=False)


class BulkSendRegistrationInvitationsSerializer(Serializer):
    invitation_ids = ListField(child=IntegerField(), allow_empty=False, max_length=500)


class ClearRegistrationInvitationsSerializer(Serializer):
    SCOPE_INACTIVE = 'inactive'
    SCOPE_ALL = 'all'

    scope = ChoiceField(
        choices=[(SCOPE_INACTIVE, 'inactive'), (SCOPE_ALL, 'all')],
        default=SCOPE_INACTIVE,
        required=False,
    )


class ValidateInvitationSerializer(Serializer):
    valid = BooleanField(read_only=True)
    email = CharField(read_only=True, allow_null=True)
    expires_at = DateTimeField(read_only=True, allow_null=True)
    status = CharField(read_only=True, allow_null=True)
