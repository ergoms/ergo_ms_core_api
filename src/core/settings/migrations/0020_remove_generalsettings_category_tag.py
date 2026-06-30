from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ('settings', '0019_alter_generalsettings_site_name'),
    ]

    operations = [
        migrations.DeleteModel(
            name='Tag',
        ),
        migrations.DeleteModel(
            name='Category',
        ),
        migrations.DeleteModel(
            name='GeneralSettings',
        ),
    ]
