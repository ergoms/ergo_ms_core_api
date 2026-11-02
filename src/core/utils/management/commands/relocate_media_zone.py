"""Перенос уже лежащих файлов удалённой зоны на её media_api.

Чтение старых файлов до переноса идёт с местного диска. Команда копирует
их на адрес зоны и после совпадения размера удаляет местную копию.
Повторный запуск пропускает файлы, которые на той стороне уже того же размера.

    ergoms api relocate_media_zone --dry-run
    ergoms api relocate_media_zone
"""

from __future__ import annotations

import os
from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError

from core.shared.media_zone_http import MediaZoneError, zone_meta, zone_save
from core.shared.media_zones import MediaZone, load_media_zones


class Command(BaseCommand):
    help = 'Перенести местные файлы удалённых зон media на их media_api'

    def add_arguments(self, parser):
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Только посчитать местные файлы, ничего не копировать',
        )
        parser.add_argument(
            '--keep-local',
            action='store_true',
            help='Скопировать, но не удалять местную копию',
        )
        parser.add_argument(
            '--prefix',
            action='append',
            default=[],
            help='Только этот префикс. Можно повторить',
        )

    def handle(self, *args, **options):
        zones = [zone for zone in load_media_zones() if zone.mode == 'remote']
        wanted = {item.strip().strip('/') for item in options['prefix'] if item.strip()}
        if wanted:
            zones = [zone for zone in zones if zone.prefix in wanted]
            missing = wanted - {zone.prefix for zone in zones}
            if missing:
                raise CommandError(
                    'Нет включённой удалённой зоны: ' + ', '.join(sorted(missing))
                )
        if not zones:
            raise CommandError(
                'Включённых удалённых зон нет. Задайте адрес в media_zones.yaml '
                '(переменная MEDIA_ZONE_ARCHIVE_URL) и перезапустите процессы.'
            )

        root = Path(settings.MEDIA_ROOT).resolve()
        dry_run = bool(options['dry_run'])
        keep_local = bool(options['keep_local'])
        failures = 0
        for zone in zones:
            copied, skipped, failed, removed = self._relocate_zone(
                root, zone, dry_run=dry_run, keep_local=keep_local,
            )
            failures += failed
            if dry_run:
                self.stdout.write(f'{zone.prefix}: к переносу {copied} файлов')
            else:
                self.stdout.write(
                    f'{zone.prefix}: скопировано {copied}, уже было {skipped}, '
                    f'ошибок {failed}, удалено местных {removed}'
                )
        if failures:
            raise CommandError(f'Перенос закончился с ошибками: {failures}')

    def _relocate_zone(
        self,
        root: Path,
        zone: MediaZone,
        *,
        dry_run: bool,
        keep_local: bool,
    ) -> tuple[int, int, int, int]:
        base = (root / zone.prefix).resolve()
        if not base.is_relative_to(root) or not base.is_dir():
            self.stdout.write(f'{zone.prefix}: местного каталога нет, переносить нечего')
            return 0, 0, 0, 0
        self.stdout.write(f'{zone.prefix} → {zone.base_url}')
        copied = skipped = failed = removed = 0
        seen = 0
        for dirpath, _dirnames, filenames in os.walk(base):
            for name in filenames:
                src = Path(dirpath) / name
                if src.is_symlink() or not src.is_file():
                    continue
                try:
                    relative = src.resolve().relative_to(root).as_posix()
                except ValueError:
                    continue
                if not (relative == zone.prefix or relative.startswith(zone.prefix + '/')):
                    continue
                seen += 1
                size = src.stat().st_size
                if size == 0:
                    self.stderr.write(f'пустой файл пропущен: {relative}')
                    failed += 1
                    continue
                if dry_run:
                    copied += 1
                    if seen % 5000 == 0:
                        self.stdout.write(f'{zone.prefix}: просмотрено {seen}')
                    continue
                try:
                    exists, remote_size = zone_meta(zone.base_url, zone.key, relative)
                    if exists and remote_size == size:
                        skipped += 1
                    else:
                        with src.open('rb') as handle:
                            zone_save(zone.base_url, zone.key, relative, handle)
                        exists, remote_size = zone_meta(zone.base_url, zone.key, relative)
                        if not exists or remote_size != size:
                            raise MediaZoneError(
                                f'размер на той стороне {remote_size}, местный {size}'
                            )
                        copied += 1
                    if not keep_local:
                        src.unlink()
                        removed += 1
                except (OSError, MediaZoneError) as exc:
                    failed += 1
                    self.stderr.write(f'{relative}: {exc}')
                if seen % 2000 == 0:
                    self.stdout.write(
                        f'{zone.prefix}: просмотрено {seen}, скопировано {copied}, '
                        f'уже было {skipped}, ошибок {failed}'
                    )
        if not dry_run and not keep_local:
            _remove_empty_dirs(base)
        return copied, skipped, failed, removed


def _remove_empty_dirs(base: Path) -> None:
    for dirpath, _dirnames, _filenames in os.walk(base, topdown=False):
        current = Path(dirpath)
        if current == base:
            continue
        try:
            next(current.iterdir())
        except StopIteration:
            current.rmdir()
        except OSError:
            continue
