from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ('settings', '0020_remove_generalsettings_category_tag'),
    ]

    operations = [
        migrations.DeleteModel(
            name='AppearanceSettings',
        ),
    ]
