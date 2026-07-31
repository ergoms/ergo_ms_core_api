# Generated manually for SMTP password at-rest encryption.

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('settings', '0037_alter_theme_is_default_alter_theme_module_key_and_more'),
    ]

    operations = [
        migrations.AlterField(
            model_name='emailsettings',
            name='password',
            field=models.CharField(
                blank=True,
                max_length=512,
                verbose_name='SMTP Password',
            ),
        ),
    ]
