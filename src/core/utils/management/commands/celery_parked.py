"""Задачи модулей, которые оборвал перезапуск воркера и которые ждут решения.

Пример:
>>> ergoms celery-parked
>>> ergoms celery-parked --resume <id>
>>> ergoms celery-parked --resume --all --module=<name>
>>> ergoms celery-parked --drop <id>
"""

import json
import time

from django.core.management.base import BaseCommand, CommandError

from src.config.celery import celery_app, ensure_django_celery_configured
from src.core.utils.celery.restart_hold import parked_tasks
from src.core.utils.celery.restart_store import get_restart_store
from src.core.utils.log_i18n import log_t


def _tag(kind: str, text: str) -> str:
    # log_t уже положил core/deployment в sys.path.
    from console_tags import format_console

    return format_console(kind, text)


def _when(stamp) -> str:
    try:
        return time.strftime('%Y-%m-%d %H:%M', time.localtime(float(stamp)))
    except (TypeError, ValueError):
        return '-'


def _short_kwargs(kwargs: dict, limit: int = 160) -> str:
    text = json.dumps(kwargs or {}, ensure_ascii=False, default=str)
    return text if len(text) <= limit else text[: limit - 1] + '…'


class Command(BaseCommand):
    help = 'Отложенные после перезапуска задачи Celery: список, продолжить, удалить'

    def add_arguments(self, parser):
        parser.add_argument('--resume', nargs='*', metavar='ID', help='Поставить задачи снова')
        parser.add_argument('--drop', nargs='*', metavar='ID', help='Удалить без запуска')
        parser.add_argument('--all', action='store_true', help='Все отложенные (с учётом --module)')
        parser.add_argument('--module', default='', help='Только задачи modules/<name>')
        parser.add_argument('--json', action='store_true', help='Список в JSON')

    def handle(self, *args, **options):
        ensure_django_celery_configured()
        prefix = f"modules.{options['module']}." if options['module'] else ''
        items = sorted(parked_tasks(prefix, app=celery_app), key=lambda item: item.get('parked_at') or 0)

        if options['resume'] is not None:
            return self._apply(items, options['resume'], options['all'], self._resume)
        if options['drop'] is not None:
            return self._apply(items, options['drop'], options['all'], self._drop)
        self._list(items, as_json=options['json'])

    def _list(self, items: list[dict], *, as_json: bool) -> None:
        if as_json:
            self.stdout.write(json.dumps(items, ensure_ascii=False, indent=2, default=str))
            return
        if not items:
            self.stdout.write(_tag('ok', log_t('celery_parked_none')))
            return
        self.stdout.write(_tag('warning', log_t('celery_parked_header', count=len(items))))
        for item in items:
            self.stdout.write(
                log_t(
                    'celery_parked_row',
                    id=item.get('id'),
                    task=item.get('task'),
                    queue=item.get('queue') or '-',
                    parked_at=_when(item.get('parked_at')),
                    resume=item.get('resume_kwarg') or '-',
                )
            )
            self.stdout.write(f"    {_short_kwargs(item.get('kwargs'))}")
        self.stdout.write(log_t('celery_parked_hint'))

    def _apply(self, items: list[dict], ids: list[str], take_all: bool, action) -> None:
        if take_all:
            targets = [item['id'] for item in items]
        elif ids:
            targets = ids
        else:
            raise CommandError(log_t('celery_parked_need_target'))
        store = get_restart_store(celery_app)
        for parked_id in targets:
            record = store.unpark(parked_id)
            if record is None:
                self.stdout.write(_tag('warning', log_t('celery_parked_not_found', id=parked_id)))
                continue
            action(record, store)

    def _resume(self, record: dict, store) -> None:
        kwargs = dict(record.get('kwargs') or {})
        resume_kwarg = record.get('resume_kwarg')
        if resume_kwarg:
            kwargs[resume_kwarg] = True
        try:
            result = celery_app.send_task(
                record['task'],
                args=list(record.get('args') or []),
                kwargs=kwargs,
                queue=record.get('queue') or None,
            )
        except Exception as exc:
            # Не потерять задачу, если брокер не принял сообщение.
            store.park(record)
            self.stdout.write(_tag('error', log_t('celery_parked_send_failed', id=record['id'], error=exc)))
            return
        self.stdout.write(
            _tag(
                'ok',
                log_t(
                    'celery_parked_resumed',
                    task=record['task'],
                    queue=record.get('queue') or 'default',
                    new_id=result.id,
                ),
            )
        )

    def _drop(self, record: dict, _store) -> None:
        self.stdout.write(_tag('ok', log_t('celery_parked_dropped', id=record['id'], task=record['task'])))
