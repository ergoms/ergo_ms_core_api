from django.contrib.postgres.indexes import GinIndex
from django.contrib.postgres.operations import TrigramExtension
from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ('core_audit', '0001_initial'),
    ]

    operations = [
        TrigramExtension(),
        migrations.AddIndex(
            model_name='auditevent',
            index=GinIndex(
                fields=['actor_label'],
                name='audit_actor_label_trgm',
                opclasses=['gin_trgm_ops'],
            ),
        ),
        migrations.AddIndex(
            model_name='auditevent',
            index=GinIndex(
                fields=['entity_label'],
                name='audit_entity_label_trgm',
                opclasses=['gin_trgm_ops'],
            ),
        ),
    ]
