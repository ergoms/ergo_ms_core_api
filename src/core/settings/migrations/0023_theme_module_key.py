from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('settings', '0022_auto_create_system_themes'),
    ]

    operations = [
        migrations.AddField(
            model_name='theme',
            name='module_key',
            field=models.CharField(
                blank=True,
                help_text='Ключ модуля (kebab-case). Пусто — глобальная тема сайта.',
                max_length=100,
                null=True,
                verbose_name='Модуль',
            ),
        ),
        migrations.AddField(
            model_name='theme',
            name='module_tokens',
            field=models.JSONField(
                blank=True,
                default=dict,
                help_text='Дополнительные CSS-переменные модуля (--module-*)',
                verbose_name='Токены модуля',
            ),
        ),
        migrations.AddIndex(
            model_name='theme',
            index=models.Index(fields=['module_key', 'is_active'], name='settings_th_module__a1b2c3_idx'),
        ),
        migrations.AddIndex(
            model_name='theme',
            index=models.Index(
                fields=['module_key', 'is_default'],
                name='settings_th_module__d4e5f6_idx',
            ),
        ),
    ]
