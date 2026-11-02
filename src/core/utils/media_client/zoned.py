"""Клиент с зонами. Обычные пути идут во внутренний клиент, префикс зоны — в неё.

Новая запись удалённой зоны сразу уходит на тот media_api. Чтение, если там
файла ещё нет, берёт местный корень: перенос не обрывает уже сохранённые страницы.
"""

from __future__ import annotations

from typing import BinaryIO

from core.shared.media_zone_http import (
    zone_delete,
    zone_download,
    zone_meta,
    zone_open,
    zone_save,
)
from core.shared.media_zones import MediaZone, match_media_zone

from .local import LocalMediaClient
from .path_utils import normalize_media_path
from .pipeline import MediaPipelineMixin


class ZonedMediaClient(MediaPipelineMixin):
    def __init__(self, inner, zones: tuple[MediaZone, ...]):
        self._inner = inner
        self._zones = zones
        self._local_zones: dict[str, LocalMediaClient] = {}

    @property
    def root_path(self) -> str:
        return self._inner.root_path

    def normalize_path(self, file_path: str) -> str:
        normalized = normalize_media_path(file_path)
        if match_media_zone(normalized, self._zones) is None:
            return self._inner.normalize_path(normalized)
        return normalized

    def _local_zone(self, zone: MediaZone) -> LocalMediaClient:
        client = self._local_zones.get(zone.prefix)
        if client is None:
            client = LocalMediaClient(zone.root, create=False)
            self._local_zones[zone.prefix] = client
        return client

    def _remote_exists(self, zone: MediaZone, path: str) -> bool:
        exists, _size = zone_meta(zone.base_url, zone.key, path)
        return exists

    def exists(self, path: str) -> bool:
        normalized = self.normalize_path(path)
        zone = match_media_zone(normalized, self._zones)
        if zone is None:
            return self._inner.exists(normalized)
        if zone.mode == 'local':
            return self._local_zone(zone).exists(normalized)
        if self._remote_exists(zone, normalized):
            return True
        return self._inner.exists(normalized)

    def open(self, path: str, mode: str = 'rb') -> BinaryIO:
        if 'w' in mode or 'a' in mode or '+' in mode:
            raise ValueError('ZonedMediaClient.open поддерживает только чтение')
        normalized = self.normalize_path(path)
        zone = match_media_zone(normalized, self._zones)
        if zone is None:
            return self._inner.open(normalized, mode)
        if zone.mode == 'local':
            return self._local_zone(zone).open(normalized, mode)
        if self._remote_exists(zone, normalized):
            return zone_open(zone.base_url, zone.key, normalized)
        return self._inner.open(normalized, mode)

    def read_bytes(self, path: str) -> bytes:
        with self.open(path, 'rb') as handle:
            return handle.read()

    def save(self, path: str, content: BinaryIO | bytes) -> str:
        normalized = self.normalize_path(path)
        zone = match_media_zone(normalized, self._zones)
        if zone is None:
            return self._inner.save(normalized, content)
        if zone.mode == 'local':
            return self._local_zone(zone).save(normalized, content)
        return zone_save(zone.base_url, zone.key, normalized, content)

    def delete(self, path: str) -> bool:
        normalized = self.normalize_path(path)
        zone = match_media_zone(normalized, self._zones)
        if zone is None:
            return self._inner.delete(normalized)
        if zone.mode == 'local':
            return self._local_zone(zone).delete(normalized)
        remote_deleted = zone_delete(zone.base_url, zone.key, normalized)
        local_deleted = self._inner.delete(normalized)
        return remote_deleted or local_deleted

    def size(self, path: str) -> int:
        normalized = self.normalize_path(path)
        zone = match_media_zone(normalized, self._zones)
        if zone is None:
            return self._inner.size(normalized)
        if zone.mode == 'local':
            return self._local_zone(zone).size(normalized)
        exists, remote_size = zone_meta(zone.base_url, zone.key, normalized)
        if exists:
            return remote_size
        return self._inner.size(normalized)

    def local_source_path(self, path: str) -> str | None:
        normalized = self.normalize_path(path)
        zone = match_media_zone(normalized, self._zones)
        if zone is None:
            return self._inner.local_source_path(normalized)
        if zone.mode == 'local':
            return self._local_zone(zone).local_source_path(normalized)
        if self._remote_exists(zone, normalized):
            return None
        return self._inner.local_source_path(normalized)

    def download_to(self, path: str, dest: str) -> None:
        normalized = self.normalize_path(path)
        zone = match_media_zone(normalized, self._zones)
        if zone is not None and zone.mode == 'remote' and self._remote_exists(zone, normalized):
            zone_download(zone.base_url, zone.key, normalized, dest)
            return
        if zone is not None and zone.mode == 'local':
            self._local_zone(zone).download_to(normalized, dest)
            return
        self._inner.download_to(normalized, dest)

    def commit_local(self, local_path: str, target: str) -> str:
        normalized = self.normalize_path(target)
        zone = match_media_zone(normalized, self._zones)
        if zone is None:
            return self._inner.commit_local(local_path, normalized)
        if zone.mode == 'local':
            return self._local_zone(zone).commit_local(local_path, normalized)
        with open(local_path, 'rb') as handle:
            return zone_save(zone.base_url, zone.key, normalized, handle)
