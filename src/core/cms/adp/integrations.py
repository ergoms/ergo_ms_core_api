"""Platform-ops ADP для распределённого входа."""

from __future__ import annotations

from src.core.cms.adp.services.session_devices import is_device_session_active
from src.core.integrations import bridge
from src.core.integrations.module_contracts import SESSION_DEVICE_ACTIVE


@bridge.provide_op(SESSION_DEVICE_ACTIVE)
def _session_device_active(*, user_id=None, device_id=None, user_public_id=None, **_):
    if device_id is None:
        return False
    from django.contrib.auth import get_user_model

    User = get_user_model()
    user = None
    if user_id is not None:
        user = User.objects.filter(pk=user_id).first()
    if user is None and user_public_id:
        user = User.objects.filter(public_id=user_public_id).first()
    if user is None or not user.is_active:
        return False
    return bool(is_device_session_active(user, device_id))
