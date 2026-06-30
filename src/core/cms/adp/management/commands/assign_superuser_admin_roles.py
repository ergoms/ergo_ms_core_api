# -*- coding: utf-8 -*-
"""
Management command: назначить ADP-роль «Администратор» всем суперюзерам без активной этой роли.
"""

from django.contrib.auth.models import User
from django.core.management.base import BaseCommand, CommandError
from django.db import OperationalError, ProgrammingError

from src.core.cms.adp.models import UserRole
from src.core.cms.adp.services.permissions import PermissionService


class Command(BaseCommand):
    help = (
        'Назначает глобальную роль «Администратор» суперюзерам, '
        'у которых ещё нет активной этой роли.'
    )

    def add_arguments(self, parser):
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Показать затронутых пользователей без записи в БД.',
        )

    def handle(self, *args, **options):
        dry_run = options['dry_run']

        try:
            admin_role = PermissionService._get_or_create_admin_role()
        except (OperationalError, ProgrammingError) as exc:
            raise CommandError(
                'Не удалось получить роль «Администратор». '
                'Убедитесь, что миграции ADP применены (ergoms db-migrate). '
                f'Ошибка: {exc}'
            ) from exc

        superusers = User.objects.filter(is_superuser=True).order_by('username')
        if not superusers.exists():
            self.stdout.write('Суперюзеры не найдены.')
            return

        assigned = 0
        skipped = 0
        errors = 0

        for user in superusers:
            has_admin_role = UserRole.objects.filter(
                user=user,
                role=admin_role,
                is_active=True,
            ).exists()

            if has_admin_role:
                skipped += 1
                self.stdout.write(f'  пропуск: {user.username} (роль уже назначена)')
                continue

            if dry_run:
                assigned += 1
                self.stdout.write(f'  будет назначено: {user.username}')
                continue

            try:
                PermissionService.assign_role_to_user(user, admin_role)
                assigned += 1
                self.stdout.write(self.style.SUCCESS(f'  назначено: {user.username}'))
            except Exception as exc:
                errors += 1
                self.stderr.write(self.style.ERROR(f'  ошибка для {user.username}: {exc}'))

        prefix = '[dry-run] ' if dry_run else ''
        self.stdout.write(
            f'\n{prefix}Итого: назначено={assigned}, пропущено={skipped}, ошибок={errors}'
        )

        if errors:
            raise CommandError(f'Завершено с ошибками: {errors}')
