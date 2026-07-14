from django.db import migrations, models


def assign_default_pairs(apps, schema_editor):
    Theme = apps.get_model('settings', 'Theme')
    Theme.objects.filter(module_key__isnull=False).update(module_pair='default')


class Migration(migrations.Migration):

    dependencies = [
        ('settings', '0023_theme_module_key'),
    ]

    operations = [
        migrations.AddField(
            model_name='theme',
            name='module_pair',
            field=models.CharField(
                blank=True,
                default='',
                help_text='Идентификатор пары light+dark для модуля. Пусто — тема сайта.',
                max_length=64,
                verbose_name='Пара модульной темы',
            ),
        ),
        migrations.RunPython(assign_default_pairs, migrations.RunPython.noop),
    ]
