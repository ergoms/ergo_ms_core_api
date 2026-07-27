import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


def migrate_email_master_switch(apps, schema_editor):
    """Перенос UserProfile.email_notifications=False -> sentinel-строка ('*','*')."""
    UserProfile = apps.get_model('cms_adp', 'UserProfile')
    NotificationPreference = apps.get_model('core_notifications', 'NotificationPreference')

    # Старый план мог применить cms_adp.0044 раньше этой миграции — поля уже нет.
    if not any(f.name == 'email_notifications' for f in UserProfile._meta.get_fields()):
        return

    table = UserProfile._meta.db_table
    with schema_editor.connection.cursor() as cursor:
        columns = {
            col.name
            for col in schema_editor.connection.introspection.get_table_description(
                cursor, table,
            )
        }
    if 'email_notifications' not in columns:
        return

    disabled_user_ids = UserProfile.objects.filter(
        email_notifications=False,
    ).values_list('user_id', flat=True)

    NotificationPreference.objects.bulk_create(
        [
            NotificationPreference(
                user_id=user_id,
                source_module='*',
                event_key='*',
                channel='email',
                enabled=False,
            )
            for user_id in disabled_user_ids
        ],
        ignore_conflicts=True,
    )


def reverse_email_master_switch(apps, schema_editor):
    NotificationPreference = apps.get_model('core_notifications', 'NotificationPreference')
    NotificationPreference.objects.filter(
        source_module='*', event_key='*', channel='email',
    ).delete()


class Migration(migrations.Migration):

    dependencies = [
        ('core_notifications', '0001_initial'),
        # Поле email_notifications ещё есть; снятие — в cms_adp.0044 после этой миграции.
        ('cms_adp', '0043_menuitem_menuseparator_public_id'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.AddField(
            model_name='notification',
            name='in_app_visible',
            field=models.BooleanField(
                default=True,
                help_text='False — email-only уведомление: запись хранит данные для письма, но не отображается в inbox',
                verbose_name='Показывать в клиенте',
            ),
        ),
        migrations.CreateModel(
            name='NotificationPreference',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('source_module', models.CharField(blank=True, default='', max_length=64, verbose_name='Модуль-источник')),
                ('event_key', models.CharField(max_length=128, verbose_name='Ключ события')),
                (
                    'channel',
                    models.CharField(
                        choices=[('in_app', 'В клиенте'), ('email', 'По эл. почте')],
                        max_length=16,
                        verbose_name='Канал',
                    ),
                ),
                ('enabled', models.BooleanField(verbose_name='Включено')),
                ('updated_at', models.DateTimeField(auto_now=True, verbose_name='Обновлено')),
                (
                    'user',
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name='core_notification_preferences',
                        to=settings.AUTH_USER_MODEL,
                        verbose_name='Пользователь',
                    ),
                ),
            ],
            options={
                'verbose_name': 'Настройка уведомлений',
                'verbose_name_plural': 'Настройки уведомлений',
            },
        ),
        migrations.AddConstraint(
            model_name='notificationpreference',
            constraint=models.UniqueConstraint(
                fields=('user', 'source_module', 'event_key', 'channel'),
                name='uniq_user_event_channel_pref',
            ),
        ),
        migrations.AddIndex(
            model_name='notificationpreference',
            index=models.Index(fields=['user', 'channel'], name='core_notif_pref_user_idx'),
        ),
        migrations.CreateModel(
            name='NotificationEmailDelivery',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('recipient_email', models.EmailField(max_length=254, verbose_name='Email получателя')),
                (
                    'status',
                    models.CharField(
                        choices=[
                            ('pending', 'Ожидает'),
                            ('sent', 'Отправлено'),
                            ('failed', 'Ошибка'),
                            ('skipped', 'Пропущено'),
                        ],
                        default='pending',
                        max_length=16,
                        verbose_name='Статус',
                    ),
                ),
                ('sent_at', models.DateTimeField(blank=True, null=True, verbose_name='Отправлено в')),
                ('error_message', models.TextField(blank=True, default='', verbose_name='Ошибка')),
                ('created_at', models.DateTimeField(auto_now_add=True, verbose_name='Создано')),
                (
                    'notification',
                    models.OneToOneField(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name='email_delivery',
                        to='core_notifications.notification',
                        verbose_name='Уведомление',
                    ),
                ),
            ],
            options={
                'verbose_name': 'Email-доставка уведомления',
                'verbose_name_plural': 'Email-доставки уведомлений',
            },
        ),
        migrations.RunPython(migrate_email_master_switch, reverse_email_master_switch),
    ]
