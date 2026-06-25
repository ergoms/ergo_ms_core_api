"""
Утилита для генерации подписанных URL и upload-токенов для медиа-сервиса.
Содержит HMAC-логику подписи, используемую core/api.
media_server/signing.py реимпортирует те же функции для media_api.
"""

import hashlib
import hmac
import time
import json
import base64

from django.conf import settings


def sign_url(path: str, secret_key: str, expires_in: int = 3600) -> tuple:
    expires = int(time.time()) + expires_in
    message = f"{path}:{expires}"
    signature = hmac.new(
        secret_key.encode('utf-8'),
        message.encode('utf-8'),
        hashlib.sha256,
    ).hexdigest()
    return signature, expires


def create_upload_token(payload: dict, secret_key: str, expires_in: int = 300) -> str:
    data = dict(payload)
    data['expires'] = int(time.time()) + expires_in
    payload_json = json.dumps(data, sort_keys=True)
    signature = hmac.new(
        secret_key.encode('utf-8'),
        payload_json.encode('utf-8'),
        hashlib.sha256,
    ).hexdigest()
    token_data = {'payload': data, 'signature': signature}
    return base64.urlsafe_b64encode(
        json.dumps(token_data).encode('utf-8')
    ).decode('utf-8')


def _get_secret_key() -> str:
    return settings.SECRET_KEY


def _get_media_base_url() -> str:
    host = getattr(settings, 'MEDIA_API_HOST', 'localhost')
    port = getattr(settings, 'MEDIA_API_PORT', 8003)
    protocol = getattr(settings, 'MEDIA_API_PROTOCOL', 'http')
    if (protocol == 'http' and int(port) == 80) or (protocol == 'https' and int(port) == 443):
        return f"{protocol}://{host}"
    return f"{protocol}://{host}:{port}"


def get_signed_media_url(
    file_path: str,
    expires_in: int = None,
) -> str:
    """
    Сгенерировать подписанный URL для доступа к медиафайлу.

    Args:
        file_path: относительный путь к файлу (например, 'avatars/123.jpg')
        expires_in: время жизни URL в секундах (по умолчанию из настроек)

    Returns:
        Полный подписанный URL для media_api.
    """
    if expires_in is None:
        expires_in = getattr(settings, 'MEDIA_URL_EXPIRATION', 3600)

    signature, expires = sign_url(file_path, _get_secret_key(), expires_in)
    base_url = _get_media_base_url()
    return f"{base_url}/serve/{file_path}?signature={signature}&expires={expires}"


def get_signed_media_url_from_field(file_field, expires_in: int = None) -> str:
    """
    Сгенерировать подписанный URL из Django FileField/ImageField.

    Args:
        file_field: экземпляр FileField или ImageField
        expires_in: время жизни URL в секундах

    Returns:
        Подписанный URL или None если файл отсутствует.
    """
    if not file_field or not file_field.name:
        return None
    return get_signed_media_url(file_field.name, expires_in)


def generate_upload_token(
    user_id: int,
    target_dir: str = '',
    max_size: int = None,
    allowed_types: list = None,
    expires_in: int = None,
) -> str:
    """
    Сгенерировать upload-токен для загрузки файла в media_api.

    Args:
        user_id: ID пользователя
        target_dir: целевая директория (например, 'tasks/attachments')
        max_size: максимальный размер файла в байтах
        allowed_types: список разрешённых расширений (например, ['pdf', 'docx'])
        expires_in: время жизни токена в секундах

    Returns:
        Подписанный base64-токен.
    """
    if max_size is None:
        max_size = getattr(settings, 'MEDIA_UPLOAD_MAX_SIZE', 104857600)

    if expires_in is None:
        expires_in = getattr(settings, 'MEDIA_UPLOAD_TOKEN_EXPIRATION', 300)

    payload = {
        'user_id': user_id,
        'target_dir': target_dir,
    }
    if max_size:
        payload['max_size'] = max_size
    if allowed_types:
        payload['allowed_types'] = allowed_types

    return create_upload_token(payload, _get_secret_key(), expires_in)


def get_upload_info(
    user_id: int,
    target_dir: str = '',
    max_size: int = None,
    allowed_types: list = None,
) -> dict:
    """
    Получить полную информацию для загрузки (URL + токен).

    Returns:
        Словарь с upload_url и token.
    """
    token = generate_upload_token(user_id, target_dir, max_size, allowed_types)
    base_url = _get_media_base_url()
    return {
        'upload_url': f"{base_url}/upload/",
        'token': token,
    }
