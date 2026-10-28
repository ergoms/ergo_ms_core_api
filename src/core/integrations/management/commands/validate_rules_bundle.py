"""Один подъём Django для проверок из ergoms core-rules-check.

Изоляция ядра валит процесс. Отчёт по modules/ — нет.
Схемы контрактов моста валят процесс.
"""

from __future__ import annotations

import json
from io import StringIO

from django.core.management import call_command
from django.core.management.base import BaseCommand, CommandError


def _run_check(name: str, **options) -> dict[str, object]:
    buffer = StringIO()
    failed = False
    try:
        call_command(name, stdout=buffer, stderr=buffer, skip_checks=True, **options)
    except CommandError:
        failed = True
    return {'failed': failed, 'text': buffer.getvalue()}


class Command(BaseCommand):
    help = (
        'Изоляция ядра, отчёт по модулям и схемы контрактов моста '
        'в одном процессе Django.'
    )

    def handle(self, *args, **options):
        payload = {
            'core': _run_check(
                'validate_module_isolation',
                scope='core',
                fail_on_warning=True,
            ),
            'modules': _run_check(
                'validate_module_isolation',
                scope='modules',
                fail_on_warning=False,
            ),
            'bridge': _run_check(
                'validate_bridge_contracts',
                fail_on_warning=True,
            ),
        }
        self.stdout.write(json.dumps(payload, ensure_ascii=False))
        if payload['core']['failed'] or payload['bridge']['failed']:
            raise CommandError('Проверки изоляции или контрактов не прошли.')
