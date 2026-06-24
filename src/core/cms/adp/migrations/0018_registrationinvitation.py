# Generated manually

from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ('cms_adp', '0017_remove_security_settings_menu'),
    ]

    operations = [
        migrations.CreateModel(
            name='RegistrationInvitation',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('email', models.EmailField(max_length=254, verbose_name='Email')),
                ('token', models.CharField(db_index=True, max_length=64, unique=True, verbose_name='Токен')),
                ('note', models.CharField(blank=True, default='', max_length=255, verbose_name='Примечание')),
                ('expires_at', models.DateTimeField(verbose_name='Действует до')),
                ('used_at', models.DateTimeField(blank=True, null=True, verbose_name='Использовано')),
                ('is_revoked', models.BooleanField(default=False, verbose_name='Отозвано')),
                ('created_at', models.DateTimeField(auto_now_add=True, verbose_name='Создано')),
                (
                    'invited_by',
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name='sent_registration_invitations',
                        to=settings.AUTH_USER_MODEL,
                        verbose_name='Пригласил',
                    ),
                ),
                (
                    'used_by',
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name='registration_invitation',
                        to=settings.AUTH_USER_MODEL,
                        verbose_name='Зарегистрировался',
                    ),
                ),
            ],
            options={
                'verbose_name': 'Приглашение на регистрацию',
                'verbose_name_plural': 'Приглашения на регистрацию',
                'ordering': ['-created_at'],
            },
        ),
    ]
