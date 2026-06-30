import os

from django.conf import settings
from django.core.files.storage import Storage

from src.core.utils.media_client import get_media_client


class MediaApiStorage(Storage):
    """
    Django Storage: операции с файлами через MediaClient (local или remote),
    публичные URL — подписанные ссылки на media_api.
    """

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self._client = None

    @property
    def client(self):
        if self._client is None:
            self._client = get_media_client()
        return self._client

    @property
    def location(self):
        return self.client.root_path

    def get_available_name(self, name, max_length=None):
        name = self.client.normalize_path(name)
        if not self.exists(name):
            return name
        directory, file_name = os.path.split(name)
        root, extension = os.path.splitext(file_name)
        index = 1
        candidate = name
        while self.exists(candidate):
            candidate_name = f'{root}_{index}{extension}'
            candidate = (
                os.path.join(directory, candidate_name).replace('\\', '/')
                if directory else candidate_name
            )
            index += 1
        return candidate

    def _open(self, name, mode='rb'):
        return self.client.open(name, mode)

    def _save(self, name, content):
        return self.client.save(name, content)

    def delete(self, name):
        self.client.delete(name)

    def exists(self, name):
        if not name:
            return False
        try:
            return self.client.exists(name)
        except ValueError:
            return False

    def size(self, name):
        return self.client.size(name)

    def url(self, name):
        from src.core.utils.media_signing import get_signed_media_url
        return get_signed_media_url(name)

    def path(self, name):
        if getattr(settings, 'MEDIA_ACCESS_MODE', 'local').strip().lower() != 'local':
            raise NotImplementedError('path() недоступен при MEDIA_ACCESS_MODE=remote')
        from pathlib import Path
        normalized = self.client.normalize_path(name)
        return str(Path(settings.MEDIA_ROOT) / normalized)
