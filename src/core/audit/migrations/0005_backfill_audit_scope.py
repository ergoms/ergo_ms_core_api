"""Backfill AuditEvent.scope из legacy-колонок измерений.

Выполняется до удаления колонок (0006): переносит значения в JSON-поле
scope для существующих записей журнала.
"""

from django.db import migrations


def backfill_scope(apps, schema_editor):
    AuditEvent = apps.get_model('core_audit', 'AuditEvent')

    batch = []
    qs = (
        AuditEvent.objects
        .exclude(organization_id__isnull=True, department_id__isnull=True)
        .only('id', 'scope', 'organization_id', 'department_id')
        .iterator(chunk_size=2000)
    )
    for event in qs:
        scope = dict(event.scope or {})
        changed = False
        if event.organization_id is not None and scope.get('organization') != event.organization_id:
            scope['organization'] = event.organization_id
            changed = True
        if event.department_id is not None and scope.get('department') != event.department_id:
            scope['department'] = event.department_id
            changed = True
        if changed:
            event.scope = scope
            batch.append(event)
        if len(batch) >= 2000:
            AuditEvent.objects.bulk_update(batch, ['scope'])
            batch = []

    if batch:
        AuditEvent.objects.bulk_update(batch, ['scope'])


def reverse_backfill(apps, schema_editor):
    # scope сохраняется; обратный перенос в колонки не требуется.
    pass


class Migration(migrations.Migration):

    dependencies = [
        ('core_audit', '0004_auditevent_scope'),
    ]

    operations = [
        migrations.RunPython(backfill_scope, reverse_backfill),
    ]
