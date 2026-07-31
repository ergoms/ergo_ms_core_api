"""Временное хранение паролей импортированных пользователей для одноразовой выгрузки."""

from __future__ import annotations

import json
import os
import re
import tempfile
from datetime import datetime
from io import BytesIO
from pathlib import Path
from typing import Any, Optional

import pandas as pd
from django.conf import settings
from django.contrib.auth import get_user_model
from django.utils.translation import gettext as _

User = get_user_model()
from django.utils import timezone

from src.core.cms.adp.services.permissions import PermissionService
from src.core.utils.secret_box import decrypt_bytes, encrypt_bytes

# TTL кэша паролей импорта (после истечения файл удаляется).
STORAGE_TTL_SECONDS = 6 * 60 * 60
_TASK_ID_PATTERN = re.compile(r'^[a-f0-9\-]{8,128}$', re.IGNORECASE)


class ImportPasswordsAccessError(Exception):
    def __init__(self, message: str, status_code: int = 403):
        self.message = message
        self.status_code = status_code
        super().__init__(message)


def _storage_dir() -> Path:
    base = getattr(settings, 'VIRTUAL_ENV_DIR', None)
    if base is None:
        base = Path('virtual_env')
    directory = Path(base) / 'cache' / 'import_users_passwords'
    directory.mkdir(parents=True, exist_ok=True)
    return directory


def _validate_task_id(task_id: str) -> str:
    normalized = (task_id or '').strip()
    if not normalized or not _TASK_ID_PATTERN.match(normalized):
        raise ImportPasswordsAccessError(_('Некорректный идентификатор задачи.'), status_code=400)
    return normalized


def _payload_path(task_id: str) -> Path:
    """Зашифрованный payload (Fernet)."""
    return _storage_dir() / f'{_validate_task_id(task_id)}.enc'


def _legacy_payload_path(task_id: str) -> Path:
    """Устаревший plaintext JSON (dual-read / cleanup)."""
    return _storage_dir() / f'{_validate_task_id(task_id)}.json'


def _read_payload(task_id: str) -> Optional[dict[str, Any]]:
    enc_path = _payload_path(task_id)
    legacy_path = _legacy_payload_path(task_id)

    payload: dict[str, Any] | None = None
    path: Path | None = None

    if enc_path.is_file():
        path = enc_path
        try:
            raw = decrypt_bytes(enc_path.read_bytes())
            if raw is None:
                enc_path.unlink(missing_ok=True)
                return None
            payload = json.loads(raw.decode('utf-8'))
        except (OSError, json.JSONDecodeError, UnicodeDecodeError):
            enc_path.unlink(missing_ok=True)
            return None
    elif legacy_path.is_file():
        path = legacy_path
        try:
            with legacy_path.open('r', encoding='utf-8') as handle:
                payload = json.load(handle)
        except (OSError, json.JSONDecodeError):
            legacy_path.unlink(missing_ok=True)
            return None

    if path is None or not isinstance(payload, dict):
        if path is not None:
            path.unlink(missing_ok=True)
        return None

    created_at = payload.get('created_at')
    if created_at:
        try:
            created = datetime.fromisoformat(created_at)
            if timezone.is_naive(created):
                created = timezone.make_aware(created, timezone.get_current_timezone())
            if (timezone.now() - created).total_seconds() > STORAGE_TTL_SECONDS:
                path.unlink(missing_ok=True)
                return None
        except (TypeError, ValueError):
            pass

    return payload


def store_import_passwords(
    task_id: str,
    initiated_by_user_id: int,
    entries: list[dict[str, str]],
) -> None:
    if not task_id or not entries:
        return

    path = _payload_path(task_id)
    payload = {
        'initiated_by_user_id': initiated_by_user_id,
        'entries': entries,
        'created_at': timezone.now().isoformat(),
    }
    blob = encrypt_bytes(json.dumps(payload, ensure_ascii=False).encode('utf-8'))

    directory = _storage_dir()
    tmp_fd, tmp_name = tempfile.mkstemp(dir=directory, suffix='.tmp')
    try:
        with os.fdopen(tmp_fd, 'wb') as handle:
            handle.write(blob)
        os.replace(tmp_name, path)
        # Убрать plaintext-legacy, если остался от старой версии.
        _legacy_payload_path(task_id).unlink(missing_ok=True)
    except Exception:
        try:
            os.unlink(tmp_name)
        except OSError:
            pass
        raise


def _user_can_access_payload(user: User, payload: dict[str, Any]) -> bool:
    if not user or not user.is_authenticated:
        return False
    initiated_by = payload.get('initiated_by_user_id')
    if initiated_by and user.id == initiated_by:
        return True
    return PermissionService.can_manage_users_as_global_admin(user)


def is_passwords_download_available(task_id: str, user: User) -> bool:
    payload = _read_payload(task_id)
    if not payload:
        return False
    entries = payload.get('entries') or []
    if not entries:
        return False
    return _user_can_access_payload(user, payload)


def consume_import_passwords(task_id: str, user: User) -> list[dict[str, str]]:
    enc_path = _payload_path(task_id)
    legacy_path = _legacy_payload_path(task_id)
    payload = _read_payload(task_id)
    if not payload:
        raise ImportPasswordsAccessError(
            _('Файл с паролями недоступен или уже был скачан.'),
            status_code=410,
        )
    if not _user_can_access_payload(user, payload):
        raise ImportPasswordsAccessError(
            _('Недостаточно прав для скачивания паролей.'),
            status_code=403,
        )

    entries = payload.get('entries') or []
    if not entries:
        enc_path.unlink(missing_ok=True)
        legacy_path.unlink(missing_ok=True)
        raise ImportPasswordsAccessError(
            _('Файл с паролями недоступен или уже был скачан.'),
            status_code=410,
        )

    enc_path.unlink(missing_ok=True)
    legacy_path.unlink(missing_ok=True)
    return entries


def build_passwords_excel(entries: list[dict[str, str]]) -> bytes:
    df = pd.DataFrame(
        entries,
        columns=['last_name', 'first_name', 'middle_name', 'username', 'email', 'password'],
    )
    df.columns = ['Фамилия', 'Имя', 'Отчество', 'Логин', 'E-mail', 'Пароль']
    buffer = BytesIO()
    df.to_excel(buffer, index=False, engine='openpyxl')
    return buffer.getvalue()
