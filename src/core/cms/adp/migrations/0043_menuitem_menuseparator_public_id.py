import uuid

from django.db import migrations, models


def backfill_public_ids(apps, schema_editor):
    MenuItem = apps.get_model('cms_adp', 'MenuItem')
    MenuSeparator = apps.get_model('cms_adp', 'MenuSeparator')
    for Model in (MenuItem, MenuSeparator):
        for row in Model.objects.filter(public_id__isnull=True).iterator():
            row.public_id = uuid.uuid4()
            row.save(update_fields=['public_id'])


class Migration(migrations.Migration):

    dependencies = [
        ('cms_adp', '0042_drop_graduate_employment_tables'),
    ]

    operations = [
        migrations.AddField(
            model_name='menuitem',
            name='public_id',
            field=models.UUIDField(editable=False, null=True, verbose_name='public id'),
        ),
        migrations.AddField(
            model_name='menuseparator',
            name='public_id',
            field=models.UUIDField(editable=False, null=True, verbose_name='public id'),
        ),
        migrations.RunPython(backfill_public_ids, migrations.RunPython.noop),
        migrations.AlterField(
            model_name='menuitem',
            name='public_id',
            field=models.UUIDField(
                default=uuid.uuid4,
                editable=False,
                unique=True,
                verbose_name='public id',
            ),
        ),
        migrations.AlterField(
            model_name='menuseparator',
            name='public_id',
            field=models.UUIDField(
                default=uuid.uuid4,
                editable=False,
                unique=True,
                verbose_name='public id',
            ),
        ),
    ]
