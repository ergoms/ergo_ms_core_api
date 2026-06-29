"""
Проверка работоспособности SMTP: конфигурация, подключение, аутентификация, отправка тестового письма.
"""

import sys

from django.core.mail import send_mail
from django.core.management.base import BaseCommand, CommandError

from src.core.utils.methods import _normalize_email_for_recipient
from src.core.utils.smtp_errors import format_smtp_error
from src.core.utils.smtp_resolver import (
    SourceType,
    build_connection,
    describe_security,
    is_email_enabled,
    resolve_connection_and_from,
    resolve_smtp_config,
    validate_config,
)

TEST_SUBJECT = 'ERGO MS: тест SMTP'
TEST_MESSAGE = 'Проверка SMTP прошла успешно.'


class Command(BaseCommand):
    help = (
        'Проверка SMTP: конфигурация, подключение, аутентификация и отправка тестового письма. '
        'Источник настроек: EmailSettings (БД) с fallback на .env.'
    )

    def add_arguments(self, parser):
        parser.add_argument(
            '--to',
            dest='recipient',
            default=None,
            help='Адрес получателя тестового письма (по умолчанию: from_email / EMAIL_HOST_USER)',
        )
        parser.add_argument(
            '--source',
            choices=['auto', 'env', 'db'],
            default='auto',
            help='Источник настроек SMTP: auto (БД → env), env или db',
        )
        parser.add_argument(
            '--check-only',
            action='store_true',
            help='Только проверить подключение и аутентификацию, без отправки письма',
        )

    def handle(self, *args, **options):
        if not is_email_enabled():
            raise CommandError(
                'Исходящая почта отключена (EMAIL_ENABLED=false). '
                'Установите EMAIL_ENABLED=true в .env для проверки SMTP.'
            )

        source: SourceType = options['source']
        check_only: bool = options['check_only']
        recipient_raw = options['recipient']

        config = resolve_smtp_config(source=source)
        missing = validate_config(config)

        if missing:
            self._fail_config(source, missing)

        assert config is not None
        source_label = 'EmailSettings' if config.source == 'db' else '.env'
        recipient = _normalize_email_for_recipient(recipient_raw or config.from_email)
        if not recipient:
            raise CommandError('Недопустимый адрес получателя. Укажите --to=email.')

        self.stdout.write(f'Источник: {config.source} ({source_label})')
        self.stdout.write(f'SMTP: {config.host}:{config.port} ({describe_security(config)})')
        self.stdout.write(f'От: {config.from_email}')
        if not check_only:
            self.stdout.write(f'Получатель: {recipient}')
        self.stdout.write('')

        self.stdout.write('[1/3] Конфигурация — OK')

        connection, from_email = resolve_connection_and_from(source=source)
        if not from_email:
            self._fail_config(source, missing)

        try:
            if connection is None:
                connection = build_connection(config)
            connection.open()
            self.stdout.write('[2/3] Подключение и аутентификация — OK')
        except Exception as exc:
            self._fail_step(2, 'Подключение и аутентификация', exc)
        finally:
            try:
                if connection is not None:
                    connection.close()
            except Exception:
                pass

        if check_only:
            self.stdout.write(self.style.SUCCESS('Проверка SMTP завершена успешно (без отправки письма).'))
            return

        try:
            send_mail(
                TEST_SUBJECT,
                TEST_MESSAGE,
                from_email,
                [recipient],
                fail_silently=False,
                connection=build_connection(config) if config.source == 'db' else None,
            )
            self.stdout.write('[3/3] Отправка тестового письма — OK')
        except Exception as exc:
            self._fail_step(3, 'Отправка тестового письма', exc)

        self.stdout.write(self.style.SUCCESS('Проверка SMTP завершена успешно.'))

    def _fail_config(self, source: SourceType, missing: list[str]):
        lines = ['Ошибка конфигурации SMTP. Отсутствуют: ' + ', '.join(missing)]
        if source == 'db':
            lines.append('Заполните EmailSettings в CMS или используйте --source=env.')
        elif source == 'auto':
            lines.append('Заполните EmailSettings в CMS или переменные EMAIL_* в .env.')
        else:
            lines.append('Проверьте переменные EMAIL_* в .env.')
        raise CommandError('\n'.join(lines))

    def _fail_step(self, step: int, label: str, exc: Exception):
        self.stderr.write(self.style.ERROR(f'[{step}/3] {label} — ОШИБКА'))
        self.stderr.write(format_smtp_error(exc))
        sys.exit(1)
