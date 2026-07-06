# Generated manually — переименование legacy-поля CMSPage.

from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ('cms', '0003_remove_legacy_cms_permission_models'),
    ]

    operations = [
        migrations.RenameField(
            model_name='cmspage',
            old_name='liminationtype',
            new_name='page_type',
        ),
    ]
