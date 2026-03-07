from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ('settings', '0017_theme'),
    ]

    operations = [
        migrations.DeleteModel(
            name='UploadedFile',
        ),
    ]
