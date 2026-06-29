from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('cms_adp', '0019_site_settings_menu_admin_only'),
    ]

    operations = [
        migrations.AddField(
            model_name='userdevice',
            name='outstanding_token_jti',
            field=models.CharField(
                blank=True,
                db_index=True,
                max_length=255,
                null=True,
                verbose_name='JTI refresh-токена',
            ),
        ),
    ]
