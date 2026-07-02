# Generated manually

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('cms_adp', '0029_userprofilechangerequest'),
    ]

    operations = [
        migrations.AddField(
            model_name='userprofilechangerequest',
            name='email',
            field=models.EmailField(blank=True, default='', max_length=254, verbose_name='Email'),
        ),
        migrations.AlterModelOptions(
            name='userprofilechangerequest',
            options={
                'ordering': ['-created_at'],
                'verbose_name': 'Заявка на изменение данных профиля',
                'verbose_name_plural': 'Заявки на изменение данных профиля',
            },
        ),
    ]
