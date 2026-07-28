# -*- coding: utf-8 -*-
"""Удаление записей мониторинга клиентов старше заданного срока."""

from django.conf import settings
from django.core.management.base import BaseCommand

from src.core.client_monitor.retention import purge_old_client_monitor


class Command(BaseCommand):
    help = (
        'Удаляет сессии мониторинга клиентов старше CLIENT_MONITORING_RETENTION_DAYS '
        '(или --days). При --dry-run только подсчитывает.'
    )

    def add_arguments(self, parser):
        parser.add_argument(
            '--days',
            type=int,
            default=None,
            help='Срок хранения в днях (переопределяет CLIENT_MONITORING_RETENTION_DAYS)',
        )
        parser.add_argument(
            '--batch-size',
            type=int,
            default=500,
            help='Размер пакета удаления (по умолчанию 500)',
        )
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Подсчитать записи без удаления',
        )

    def handle(self, *args, **options):
        days = options['days']
        if days is None:
            days = getattr(settings, 'CLIENT_MONITORING_RETENTION_DAYS', 0)

        if days <= 0 and not options['dry_run']:
            self.stderr.write(
                self.style.WARNING(
                    'CLIENT_MONITORING_RETENTION_DAYS=0 — укажите --days или задайте переменную в .env'
                )
            )
            return

        count = purge_old_client_monitor(
            retention_days=days,
            batch_size=options['batch_size'],
            dry_run=options['dry_run'],
        )

        if options['dry_run']:
            self.stdout.write(f'Будет удалено объектов: {count}')
        else:
            self.stdout.write(self.style.SUCCESS(f'Удалено объектов: {count}'))
