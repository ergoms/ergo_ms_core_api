# Generated manually — удаление неиспользуемых legacy-моделей CMS (таблицы пустые).

from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ('cms', '0001_initial'),
    ]

    operations = [
        migrations.DeleteModel(name='Accession'),
        migrations.DeleteModel(name='CMSPageComponent'),
        migrations.DeleteModel(name='ExpandedGroup'),
        migrations.DeleteModel(name='GroupURL'),
        migrations.DeleteModel(name='Object'),
        migrations.DeleteModel(name='Object_Type'),
        migrations.DeleteModel(name='Review'),
    ]
