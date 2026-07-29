"""
Проверка схем platform-дескрипторов ModuleBridge.

Использование: ergoms api validate_bridge_contracts
(входит в ergoms core-rules-check).
"""

from __future__ import annotations

from django.core.management.base import BaseCommand, CommandError

from src.core.integrations.contract_validation import collect_contract_violations


class Command(BaseCommand):
    help = (
        'Проверяет схемы дескрипторов platform-контрактов ModuleBridge '
        '(session_context.claims, audit.*, notifications.*).'
    )

    def add_arguments(self, parser):
        parser.add_argument(
            '--fail-on-warning',
            action='store_true',
            help='Выходить с ненулевым кодом при наличии нарушений (для CI).',
        )

    def handle(self, *args, **options):
        violations = collect_contract_violations()
        if not violations:
            self.stdout.write(self.style.SUCCESS('Контракты ModuleBridge: нарушений нет'))
            return

        for msg in violations:
            self.stdout.write(self.style.WARNING(f'  {msg}'))

        summary = f'Контракты ModuleBridge: найдено нарушений: {len(violations)}'
        if options.get('fail_on_warning'):
            raise CommandError(summary)

        self.stdout.write(self.style.WARNING(summary))
