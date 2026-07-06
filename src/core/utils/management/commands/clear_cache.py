"""
Очистка и инвалидация кэшей ядра.

Примеры:
  ergoms api clear_cache
  ergoms api clear_cache --targets=django
  ergoms api clear_cache --targets=apps,celery,file
  ergoms api clear_cache --targets=all --warmup
"""

import logging

from django.core.management.base import BaseCommand, CommandError

from src.core.utils.cache_registry import ALL_TARGETS, invalidate_cache_targets, warmup_file_caches

logger = logging.getLogger('core.utils.commands')


class Command(BaseCommand):
    help = (
        'Инвалидация кэшей ядра. Без --targets — только Django cache (как раньше). '
        f'Цели: {", ".join(ALL_TARGETS)}'
    )

    def add_arguments(self, parser):
        parser.add_argument(
            '--targets',
            type=str,
            default='django',
            help=f'Список целей через запятую ({", ".join(ALL_TARGETS)})',
        )
        parser.add_argument(
            '--warmup',
            action='store_true',
            help='После инвалидации выполнить warmup_caches (файловые кэши)',
        )

    def handle(self, *args, **options):
        raw_targets = (options.get('targets') or 'django').strip()
        target_list = [part.strip() for part in raw_targets.split(',') if part.strip()]
        if not target_list:
            raise CommandError('Укажите хотя бы одну цель в --targets')

        logger.info('clear_cache: targets=%s', target_list)
        try:
            results = invalidate_cache_targets(target_list)
        except ValueError as exc:
            raise CommandError(str(exc)) from exc

        for target, message in results.items():
            self.stdout.write(f'  [{target}] {message}')

        if options.get('warmup'):
            msg = warmup_file_caches()
            self.stdout.write(self.style.SUCCESS(msg))

        self.stdout.write(self.style.SUCCESS('Готово'))
