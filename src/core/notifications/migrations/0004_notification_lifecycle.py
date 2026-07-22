from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('core_notifications', '0003_notification_actions'),
    ]

    operations = [
        migrations.AddField(
            model_name='notification',
            name='archived_at',
            field=models.DateTimeField(
                blank=True,
                help_text='Не показывается в колокольчике и основном списке',
                null=True,
                verbose_name='В архиве с',
            ),
        ),
        migrations.AddField(
            model_name='notification',
            name='deleted_at',
            field=models.DateTimeField(
                blank=True,
                help_text='Мягкое удаление — скрыто из UI',
                null=True,
                verbose_name='Удалено в',
            ),
        ),
        migrations.AddField(
            model_name='notification',
            name='sidebar_hidden_at',
            field=models.DateTimeField(
                blank=True,
                help_text='Не показывается в dropdown, остаётся в истории',
                null=True,
                verbose_name='Скрыто из колокольчика',
            ),
        ),
        migrations.AddIndex(
            model_name='notification',
            index=models.Index(
                fields=['recipient', 'deleted_at', 'archived_at', 'created_at'],
                name='core_notif_inbox_idx',
            ),
        ),
    ]
