from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('settings', '0032_rename_a11y_theme_abbr_names'),
    ]

    operations = [
        migrations.AddField(
            model_name='theme',
            name='defaults_snapshot',
            field=models.JSONField(
                blank=True,
                default=dict,
                help_text='Manifest-данные для сброса модульной темы (заполняется при sync-module-defaults).',
                verbose_name='Снимок начальных значений',
            ),
        ),
    ]
