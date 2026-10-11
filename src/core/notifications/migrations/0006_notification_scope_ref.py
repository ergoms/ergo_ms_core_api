from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('core_notifications', '0005_notification_inbox_restored_at_and_user_settings'),
    ]

    operations = [
        migrations.AddField(
            model_name='notification',
            name='scope_ref',
            field=models.CharField(
                blank=True,
                default='',
                help_text='Непрозрачная ссылка модуля (public_id). Пусто — видно в любом контексте.',
                max_length=64,
                verbose_name='Контекст сессии',
            ),
        ),
        migrations.AddIndex(
            model_name='notification',
            index=models.Index(
                fields=['recipient', 'scope_ref', 'created_at'],
                name='core_notif_scope_idx',
            ),
        ),
    ]
