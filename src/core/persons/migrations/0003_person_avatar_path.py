from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('core_persons', '0002_person_gender'),
    ]

    operations = [
        migrations.AddField(
            model_name='person',
            name='avatar_path',
            field=models.CharField(
                blank=True,
                default='',
                max_length=512,
                verbose_name='Путь портрета в media',
            ),
        ),
    ]