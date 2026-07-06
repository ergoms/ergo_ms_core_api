from django.core.management.base import BaseCommand, CommandError

from src.core.cms.scripts import sync_cms_pages


class Command(BaseCommand):
    help = 'Синхронизирует CMSPage с client-маршрутами (config/routes.js + client/js/routes.js модулей)'

    def add_arguments(self, parser):
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Показать изменения без фактического обновления БД',
        )
        parser.add_argument(
            '--verbose',
            action='store_true',
            help='Показать детальную информацию о процессе',
        )

    def handle(self, *args, **options):
        self.dry_run = options['dry_run']
        self.verbose = options['verbose']

        self.stdout.write(self.style.SUCCESS('Начинаю синхронизацию CMSPage...'))

        try:
            result = sync_cms_pages(remove_orphans=True, dry_run=self.dry_run)

            if self.verbose:
                self.stdout.write(
                    f'Найдено {len(result.paths)} путей '
                    f'(config/routes.js + client/js/routes.js модулей)',
                )
                self.stdout.write(f'В БД до синхронизации: {len(result.unchanged) + len(result.removed)} путей')

            self._show_statistics(result)

            if self.dry_run:
                self.stdout.write(
                    self.style.WARNING('Пробный запуск — изменения не применены.'),
                )
            else:
                self.stdout.write(self.style.SUCCESS('Синхронизация CMSPage завершена.'))

        except Exception as exc:
            raise CommandError(f'Ошибка синхронизации CMSPage: {exc}') from exc

    def _show_statistics(self, result):
        self.stdout.write('\nСтатистика изменений:')
        self.stdout.write(f'  Новых путей: {len(result.added)}')
        self.stdout.write(f'  Путей к удалению: {len(result.removed)}')
        self.stdout.write(f'  Без изменений: {len(result.unchanged)}')

        if self.verbose and result.added:
            self.stdout.write('\nНовые пути:')
            for path in sorted(result.added):
                self.stdout.write(f'   + {path}')

        if self.verbose and result.removed:
            self.stdout.write('\nПути к удалению:')
            for path in sorted(result.removed):
                self.stdout.write(f'   - {path}')
