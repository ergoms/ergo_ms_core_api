from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('cms_adp', '0068_perf_query_indexes'),
    ]

    operations = [
        migrations.AddField(
            model_name='userprofile',
            name='gender',
            field=models.CharField(
                blank=True,
                choices=[
                    ('', 'Не указан'),
                    ('male', 'Мужской'),
                    ('female', 'Женский'),
                ],
                default='',
                max_length=16,
                verbose_name='Пол',
            ),
        ),
    ]
