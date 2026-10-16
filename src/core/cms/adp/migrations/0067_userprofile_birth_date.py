from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('cms_adp', '0066_session_connection_history'),
    ]

    operations = [
        migrations.AddField(
            model_name='userprofile',
            name='birth_date',
            field=models.DateField(blank=True, null=True, verbose_name='Дата рождения'),
        ),
    ]
