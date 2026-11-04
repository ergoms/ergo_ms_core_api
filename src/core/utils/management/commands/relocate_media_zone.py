"""Перенос уже лежащих файлов удалённой зоны на её media_api.

Чтение старых файлов до переноса идёт с местного диска. Команда копирует
их на адрес зоны и после совпадения размера удаляет местную копию.
Повторный запуск пропускает файлы, которые на той стороне уже того же размера.

    ergoms api relocate_media_zone --dry-run
    ergoms api relocate_media_zone
    ergoms api relocate_media_zone --workers 8
"""

from __future__ import annotations

import os
import threading
import time
from pathlib import Path
from queue import Queue

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError

from core.shared.media_zone_http import MediaZoneError, zone_meta, zone_save
from core.shared.media_zones import MediaZone, load_media_zones

_MAX_WORKERS = 32
_ATTEMPTS = 5
_ZONE_ROUNDS = 4


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
        parser.add_argument(
            '--workers',
            type=int,
            default=1,
            help=(
                'Сколько файлов копировать одновременно. '
                f'По умолчанию 1, не больше {_MAX_WORKERS}.'
            ),
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

        workers = int(options['workers'])
        if workers < 1 or workers > _MAX_WORKERS:
            raise CommandError(f'--workers от 1 до {_MAX_WORKERS}')

        root = Path(settings.MEDIA_ROOT).resolve()
        dry_run = bool(options['dry_run'])
        keep_local = bool(options['keep_local'])
        failures = 0
        for zone in zones:
            copied = skipped = failed = removed = 0
            for round_index in range(_ZONE_ROUNDS):
                copied, skipped, failed, removed = self._relocate_zone(
                    root,
                    zone,
                    dry_run=dry_run,
                    keep_local=keep_local,
                    workers=workers,
                )
                if dry_run or failed == 0:
                    break
                self.stdout.write(
                    f'{zone.prefix}: повтор {round_index + 2}, '
                    f'ещё ошибок {failed}'
                )
                time.sleep(min(30, 2 ** round_index))
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
        workers: int,
    ) -> tuple[int, int, int, int]:
        base = (root / zone.prefix).resolve()
        if not base.is_relative_to(root) or not base.is_dir():
            self.stdout.write(f'{zone.prefix}: местного каталога нет, переносить нечего')
            return 0, 0, 0, 0
        self.stdout.write(f'{zone.prefix} → {zone.base_url}')
        if workers > 1 and not dry_run:
            self.stdout.write(f'{zone.prefix}: потоков {workers}')
        copied = skipped = failed = removed = 0
        seen = 0
        parallel = workers > 1 and not dry_run
        jobs: Queue | None = Queue(maxsize=workers * 4) if parallel else None
        stats = {'copied': 0, 'skipped': 0, 'failed': 0, 'removed': 0, 'done': 0}
        lock = threading.Lock()
        threads: list[threading.Thread] = []
        if jobs is not None:
            for index in range(workers):
                thread = threading.Thread(
                    target=_copy_worker,
                    name=f'relocate-media-{zone.prefix}-{index}',
                    args=(jobs, zone, keep_local, stats, lock, self),
                    daemon=False,
                )
                thread.start()
                threads.append(thread)
        try:
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
                        _drop_empty(src, relative, self)
                        continue
                    if dry_run:
                        copied += 1
                        if seen % 5000 == 0:
                            self.stdout.write(f'{zone.prefix}: просмотрено {seen}')
                        continue
                    if jobs is not None:
                        jobs.put((src, relative, size))
                        continue
                    file_copied, file_skipped, file_failed, file_removed, error = _copy_file(
                        zone, src, relative, size, keep_local,
                    )
                    copied += file_copied
                    skipped += file_skipped
                    failed += file_failed
                    removed += file_removed
                    if error:
                        self.stderr.write(error)
                    if seen % 2000 == 0:
                        self.stdout.write(
                            f'{zone.prefix}: просмотрено {seen}, скопировано {copied}, '
                            f'уже было {skipped}, ошибок {failed}'
                        )
        finally:
            if jobs is not None:
                for _ in threads:
                    jobs.put(None)
                for thread in threads:
                    thread.join()
        if jobs is not None:
            copied += stats['copied']
            skipped += stats['skipped']
            failed += stats['failed']
            removed += stats['removed']
        if not dry_run and not keep_local:
            _remove_empty_dirs(base)
        return copied, skipped, failed, removed


def _copy_file(
    zone: MediaZone,
    src: Path,
    relative: str,
    size: int,
    keep_local: bool,
) -> tuple[int, int, int, int, str | None]:
    last_error = None
    for attempt in range(_ATTEMPTS):
        try:
            return _copy_once(zone, src, relative, size, keep_local)
        except MediaZoneError as exc:
            last_error = _format_zone_error(relative, exc)
            if attempt + 1 >= _ATTEMPTS:
                break
            time.sleep(min(20, 2 ** attempt))
    return 0, 0, 1, 0, last_error or f'{relative}: зона не ответила'


def _format_zone_error(relative: str, exc: MediaZoneError) -> str:
    cause = exc.__cause__
    if cause is None:
        return f'{relative}: {exc}'
    return f'{relative}: {exc} ({type(cause).__name__}: {cause})'


def _drop_empty(src: Path, relative: str, command: Command) -> None:
    try:
        src.unlink()
    except OSError as exc:
        command.stderr.write(f'{relative}: пустой файл не удалён: {exc}')


def _copy_once(
    zone: MediaZone,
    src: Path,
    relative: str,
    size: int,
    keep_local: bool,
) -> tuple[int, int, int, int, str | None]:
    try:
        exists, remote_size = zone_meta(zone.base_url, zone.key, relative)
        if exists and remote_size == size:
            copied = 0
            skipped = 1
        else:
            with src.open('rb') as handle:
                zone_save(zone.base_url, zone.key, relative, handle)
            exists, remote_size = zone_meta(zone.base_url, zone.key, relative)
            if not exists or remote_size != size:
                raise MediaZoneError(
                    f'размер на той стороне {remote_size}, местный {size}'
                )
            copied = 1
            skipped = 0
        removed = 0
        # Удаление зависит от прав на каталог, не на сам файл. Сбой здесь
        # не отменяет уже принятую копию: иначе файл считается неперенесённым.
        if not keep_local:
            try:
                src.unlink()
            except OSError as exc:
                return copied, skipped, 1, 0, f'{relative}: местная копия не удалена: {exc}'
            removed = 1
        return copied, skipped, 0, removed, None
    except OSError as exc:
        return 0, 0, 1, 0, f'{relative}: {exc}'


def _copy_worker(
    jobs: Queue,
    zone: MediaZone,
    keep_local: bool,
    stats: dict[str, int],
    lock: threading.Lock,
    command: Command,
) -> None:
    while True:
        item = jobs.get()
        if item is None:
            return
        src, relative, size = item
        try:
            copied, skipped, failed, removed, error = _copy_file(
                zone, src, relative, size, keep_local,
            )
        except Exception as exc:
            copied, skipped, failed, removed = 0, 0, 1, 0
            error = f'{relative}: {exc}'
        with lock:
            stats['copied'] += copied
            stats['skipped'] += skipped
            stats['failed'] += failed
            stats['removed'] += removed
            stats['done'] += 1
            done = stats['done']
            if error:
                command.stderr.write(error)
            if done % 2000 == 0:
                command.stdout.write(
                    f'{zone.prefix}: просмотрено {done}, скопировано {stats["copied"]}, '
                    f'уже было {stats["skipped"]}, ошибок {stats["failed"]}'
                )


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
