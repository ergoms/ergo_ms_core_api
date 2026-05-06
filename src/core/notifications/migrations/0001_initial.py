import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    initial = True

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name='Notification',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('title', models.CharField(max_length=255, verbose_name='Заголовок')),
                ('body', models.TextField(blank=True, default='', verbose_name='Текст')),
                (
                    'level',
                    models.CharField(
                        choices=[
                            ('info', 'Информация'),
                            ('success', 'Успех'),
                            ('warning', 'Предупреждение'),
                            ('error', 'Ошибка'),
                        ],
                        default='info',
                        max_length=16,
                        verbose_name='Тип',
                    ),
                ),
                ('icon', models.CharField(blank=True, default='', max_length=64, verbose_name='Имя иконки')),
                ('source_module', models.CharField(blank=True, default='', max_length=64, verbose_name='Модуль-источник')),
                ('event_key', models.CharField(blank=True, default='', max_length=128, verbose_name='Ключ события')),
                ('link_url', models.CharField(blank=True, default='', max_length=512, verbose_name='URL для перехода')),
                ('route', models.JSONField(blank=True, null=True, verbose_name='Vue Router (name + params)')),
                ('meta', models.JSONField(blank=True, default=dict, verbose_name='Доп. данные')),
                ('idempotency_key', models.CharField(blank=True, max_length=255, null=True, verbose_name='Ключ идемпотентности')),
                ('is_read', models.BooleanField(default=False, verbose_name='Прочитано')),
                ('created_at', models.DateTimeField(auto_now_add=True, db_index=True, verbose_name='Создано')),
                ('read_at', models.DateTimeField(blank=True, null=True, verbose_name='Прочитано в')),
                    (
                        'recipient',
                        models.ForeignKey(
                            on_delete=django.db.models.deletion.CASCADE,
                            related_name='core_inbox_notifications',
                            to=settings.AUTH_USER_MODEL,
                            verbose_name='Получатель',
                        ),
                    ),
            ],
            options={
                'verbose_name': 'Уведомление',
                'verbose_name_plural': 'Уведомления',
                'ordering': ['-created_at'],
            },
        ),
        migrations.AddIndex(
            model_name='notification',
            index=models.Index(fields=['recipient', 'is_read', 'created_at'], name='core_notif_recipient_idx'),
        ),
        migrations.AddConstraint(
            model_name='notification',
            constraint=models.UniqueConstraint(
                condition=models.Q(('idempotency_key__isnull', False)),
                fields=('recipient', 'idempotency_key'),
                name='uniq_recipient_idem',
            ),
        ),
    ]
