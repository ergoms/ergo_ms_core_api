# Generated manually

from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ('cms_adp', '0028_rename_site_settings_menu_to_system'),
    ]

    operations = [
        migrations.CreateModel(
            name='UserProfileChangeRequest',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('first_name', models.CharField(blank=True, default='', max_length=150, verbose_name='Имя')),
                ('last_name', models.CharField(blank=True, default='', max_length=150, verbose_name='Фамилия')),
                ('middle_name', models.CharField(blank=True, default='', max_length=150, verbose_name='Отчество')),
                ('comment', models.CharField(blank=True, default='', max_length=500, verbose_name='Комментарий пользователя')),
                (
                    'status',
                    models.CharField(
                        choices=[
                            ('pending', 'На рассмотрении'),
                            ('approved', 'Одобрено'),
                            ('rejected', 'Отклонено'),
                        ],
                        db_index=True,
                        default='pending',
                        max_length=20,
                        verbose_name='Статус',
                    ),
                ),
                (
                    'admin_comment',
                    models.CharField(blank=True, default='', max_length=500, verbose_name='Комментарий администратора'),
                ),
                ('reviewed_at', models.DateTimeField(blank=True, null=True, verbose_name='Дата обработки')),
                ('created_at', models.DateTimeField(auto_now_add=True, verbose_name='Создано')),
                (
                    'reviewed_by',
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name='reviewed_profile_change_requests',
                        to=settings.AUTH_USER_MODEL,
                        verbose_name='Обработал',
                    ),
                ),
                (
                    'user',
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name='profile_change_requests',
                        to=settings.AUTH_USER_MODEL,
                        verbose_name='Пользователь',
                    ),
                ),
            ],
            options={
                'verbose_name': 'Заявка на изменение ФИО',
                'verbose_name_plural': 'Заявки на изменение ФИО',
                'ordering': ['-created_at'],
            },
        ),
        migrations.AddIndex(
            model_name='userprofilechangerequest',
            index=models.Index(fields=['user', 'status'], name='cms_adp_use_user_id_status_idx'),
        ),
    ]
