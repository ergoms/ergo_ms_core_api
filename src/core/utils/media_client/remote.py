"""Удалённый доступ к media через HTTP (media_api на отдельном сервере)."""

import logging
from io import BytesIO
from typing import BinaryIO
from urllib.parse import quote

import requests
from django.conf import settings
from django.core.exceptions import ImproperlyConfigured

from .path_utils import normalize_media_path
from .pipeline import MediaPipelineMixin

logger = logging.getLogger(__name__)

_DEFAULT_TIMEOUT = 60
_STREAM_CHUNK = 1024 * 1024


class RemoteMediaClient(MediaPipelineMixin):
    """Операции с файлами через внутренний HTTP API media_api."""

    def __init__(
        self,
        base_url: str | None = None,
        internal_key: str | None = None,
        timeout: int = _DEFAULT_TIMEOUT,
    ):
        self._base_url = (base_url or _resolve_internal_base_url()).rstrip('/')
        self._internal_key = internal_key if internal_key is not None else _resolve_internal_key()
        self._timeout = timeout
        if not self._internal_key:
            raise ImproperlyConfigured(
                'MEDIA_ACCESS_MODE=remote требует MEDIA_API_INTERNAL_KEY '
                'для служебного доступа core/api к media_api.'
            )

    @property
    def root_path(self) -> str:
        return self._base_url

    def normalize_path(self, file_path: str) -> str:
        return normalize_media_path(file_path)

    def _headers(self) -> dict[str, str]:
        return {'X-Media-Internal-Key': self._internal_key}

    def _internal_url(self, path: str, suffix: str) -> str:
        encoded = quote(self.normalize_path(path), safe='/')
        return f'{self._base_url}/internal/{suffix}/{encoded}'

    def exists(self, path: str) -> bool:
        try:
            response = requests.get(
                self._internal_url(path, 'meta'),
                headers=self._headers(),
                timeout=self._timeout,
            )
            if response.status_code == 404:
                return False
            response.raise_for_status()
            return bool(response.json().get('exists'))
        except requests.RequestException as exc:
            logger.warning('RemoteMediaClient.exists ошибка для %s: %s', path, exc)
            return False

    def open(self, path: str, mode: str = 'rb') -> BinaryIO:
        if 'w' in mode or 'a' in mode or '+' in mode:
            raise ValueError('RemoteMediaClient.open поддерживает только чтение')
        return BytesIO(self.read_bytes(path))

    def read_bytes(self, path: str) -> bytes:
        response = requests.get(
            self._internal_url(path, 'read'),
            headers=self._headers(),
            timeout=self._timeout,
        )
        if response.status_code == 404:
            raise FileNotFoundError(path)
        response.raise_for_status()
        return response.content

    def save(self, path: str, content: BinaryIO | bytes) -> str:
        normalized = self.normalize_path(path)
        if isinstance(content, (bytes, bytearray)):
            data = bytes(content)
        else:
            if hasattr(content, 'seek'):
                content.seek(0)
            data = content.read()

        response = requests.put(
            self._internal_url(normalized, 'write'),
            headers={
                **self._headers(),
                'Content-Type': 'application/octet-stream',
            },
            data=data,
            timeout=self._timeout,
        )
        response.raise_for_status()
        payload = response.json()
        return payload.get('path', normalized)

    def delete(self, path: str) -> bool:
        response = requests.delete(
            self._internal_url(path, 'delete'),
            headers=self._headers(),
            timeout=self._timeout,
        )
        if response.status_code == 404:
            return False
        response.raise_for_status()
        return bool(response.json().get('deleted'))

    def size(self, path: str) -> int:
        response = requests.get(
            self._internal_url(path, 'meta'),
            headers=self._headers(),
            timeout=self._timeout,
        )
        if response.status_code == 404:
            raise FileNotFoundError(path)
        response.raise_for_status()
        payload = response.json()
        if not payload.get('exists'):
            raise FileNotFoundError(path)
        return int(payload['size'])

    def download_to(self, path: str, dest: str) -> None:
        with requests.get(
            self._internal_url(path, 'read'),
            headers=self._headers(),
            timeout=self._timeout,
            stream=True,
        ) as response:
            if response.status_code == 404:
                raise FileNotFoundError(path)
            response.raise_for_status()
            with open(dest, 'wb') as file_obj:
                for chunk in response.iter_content(chunk_size=_STREAM_CHUNK):
                    if chunk:
                        file_obj.write(chunk)

    def commit_local(self, local_path: str, target: str) -> str:
        normalized = self.normalize_path(target)
        with open(local_path, 'rb') as file_obj:
            response = requests.put(
                self._internal_url(normalized, 'write'),
                headers={
                    **self._headers(),
                    'Content-Type': 'application/octet-stream',
                },
                data=file_obj,
                timeout=self._timeout,
            )
        response.raise_for_status()
        return response.json().get('path', normalized)


def _resolve_internal_key() -> str:
    return getattr(settings, 'MEDIA_API_INTERNAL_KEY', '') or ''


def _resolve_internal_base_url() -> str:
    return (getattr(settings, 'MEDIA_API_INTERNAL_URL', '') or '').rstrip('/')
