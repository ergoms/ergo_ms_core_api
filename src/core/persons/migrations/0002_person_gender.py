from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('core_persons', '0001_initial'),
    ]

    operations = [
        migrations.AddField(
            model_name='person',
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
