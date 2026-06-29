from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('core_notifications', '0002_preferences_email_delivery'),
    ]

    operations = [
        migrations.AddField(
            model_name='notification',
            name='actions',
            field=models.JSONField(
                blank=True,
                default=list,
                help_text='Список {id, label, style, handler} для интерактивных уведомлений',
                verbose_name='Кнопки действий',
            ),
        ),
        migrations.AddField(
            model_name='notification',
            name='actions_state',
            field=models.CharField(
                blank=True,
                help_text='null — без действий; pending / resolved / expired',
                max_length=16,
                null=True,
                verbose_name='Состояние действий',
            ),
        ),
        migrations.AddField(
            model_name='notification',
            name='resolved_action_id',
            field=models.CharField(
                blank=True,
                default='',
                max_length=64,
                verbose_name='Выбранное действие',
            ),
        ),
        migrations.AddField(
            model_name='notification',
            name='resolved_at',
            field=models.DateTimeField(
                blank=True,
                null=True,
                verbose_name='Действие выполнено в',
            ),
        ),
    ]
