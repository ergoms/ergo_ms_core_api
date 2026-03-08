from django.conf import settings
from django.core.files.storage import FileSystemStorage


class MediaApiStorage(FileSystemStorage):
    """
    Кастомный storage backend: файлы хранятся локально в MEDIA_ROOT,
    но url() возвращает подписанный URL через media_api сервис.
    """

    def __init__(self, **kwargs):
        kwargs.setdefault('location', settings.MEDIA_ROOT)
        super().__init__(**kwargs)

    def url(self, name):
        from src.core.utils.media_signing import get_signed_media_url
        return get_signed_media_url(name)
