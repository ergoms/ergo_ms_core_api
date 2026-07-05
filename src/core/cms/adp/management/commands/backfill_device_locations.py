# -*- coding: utf-8 -*-
"""Backfill city/country для UserDevice по IP через локальную GeoIP базу."""

from django.core.management.base import BaseCommand
from django.db.models import Q

from src.core.cms.adp.models import UserDevice
from src.core.utils.geoip import resolve_ip_location


class Command(BaseCommand):
    help = (
        'Заполняет city/country у UserDevice с неизвестной геолокацией '
        'по локальной DB-IP MMDB'
    )

    def add_arguments(self, parser):
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Показать статистику без записи в БД',
        )
        parser.add_argument(
            '--batch-size',
            type=int,
            default=500,
            help='Размер пакета bulk_update (по умолчанию 500)',
        )

    def handle(self, *args, **options):
        dry_run = options['dry_run']
        batch_size = max(1, options['batch_size'])

        devices = UserDevice.objects.filter(
            Q(city__isnull=True)
            | Q(country__isnull=True)
            | Q(city='')
            | Q(country='')
            | Q(city__iexact='неизвестно')
            | Q(country__iexact='неизвестно')
            | Q(city__iexact='unknown')
            | Q(country__iexact='unknown')
            | Q(city__iexact='n/a')
            | Q(country__iexact='n/a')
        ).only('id', 'ip_address', 'city', 'country')

        total = devices.count()
        if total == 0:
            self.stdout.write(self.style.SUCCESS('Нет устройств для обновления'))
            return

        ip_to_location: dict[str, tuple[str, str]] = {}
        skipped_private = 0
        pending_updates: list[UserDevice] = []
        updated_devices = 0

        for device in devices.iterator(chunk_size=batch_size):
            ip = (device.ip_address or '').strip()
            if ip not in ip_to_location:
                ip_to_location[ip] = resolve_ip_location(ip)

            city, country = ip_to_location[ip]
            if city == 'Неизвестно' and country == 'Неизвестно':
                skipped_private += 1
                continue

            if device.city == city and device.country == country:
                continue

            device.city = city
            device.country = country
            pending_updates.append(device)
            updated_devices += 1

            if len(pending_updates) >= batch_size:
                if not dry_run:
                    UserDevice.objects.bulk_update(
                        pending_updates,
                        ['city', 'country'],
                        batch_size=batch_size,
                    )
                pending_updates.clear()

        if pending_updates and not dry_run:
            UserDevice.objects.bulk_update(
                pending_updates,
                ['city', 'country'],
                batch_size=batch_size,
            )

        prefix = '[dry-run] ' if dry_run else ''
        self.stdout.write(
            f'{prefix}Всего записей: {total}; '
            f'обновлено: {updated_devices}; '
            f'пропущено (неизвестный IP): {skipped_private}; '
            f'уникальных IP: {len(ip_to_location)}'
        )
