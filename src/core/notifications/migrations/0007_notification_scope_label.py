from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('core_notifications', '0006_notification_scope_ref'),
    ]

    operations = [
        migrations.AddField(
            model_name='notification',
            name='scope_label',
            field=models.CharField(
                blank=True,
                default='',
                help_text='Человекочитаемое имя контекста сессии.',
                max_length=255,
                verbose_name='Подпись контекста',
            ),
        ),
    ]
