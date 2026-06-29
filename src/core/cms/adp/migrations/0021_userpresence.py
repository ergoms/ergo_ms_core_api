from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ('cms_adp', '0020_userdevice_outstanding_token_jti'),
    ]

    operations = [
        migrations.CreateModel(
            name='UserPresence',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('connection_count', models.PositiveIntegerField(default=0, verbose_name='Число WS-подключений')),
                ('last_seen', models.DateTimeField(blank=True, null=True, verbose_name='Последняя активность')),
                (
                    'user',
                    models.OneToOneField(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name='presence',
                        to=settings.AUTH_USER_MODEL,
                        verbose_name='Пользователь',
                    ),
                ),
            ],
            options={
                'verbose_name': 'Онлайн-статус пользователя',
                'verbose_name_plural': 'Онлайн-статусы пользователей',
            },
        ),
    ]
