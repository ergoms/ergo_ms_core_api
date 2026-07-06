# Удаление legacy CMS-моделей прав (ExpandedPermission пустая, метка AdminAccession не используется).

from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ('cms', '0002_remove_legacy_cms_models'),
    ]

    operations = [
        migrations.DeleteModel(name='ExpandedPermission'),
        migrations.DeleteModel(name='PermissionMark'),
        migrations.DeleteModel(name='GroupCategory'),
    ]
