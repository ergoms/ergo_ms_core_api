from django.db import migrations


def remove_filemanager_menu(apps, schema_editor):
    MenuItem = apps.get_model('cms_adp', 'MenuItem')
    MenuItem.objects.filter(route_name='FileManager').delete()


class Migration(migrations.Migration):

    dependencies = [
        ('cms_adp', '0013_bi_module_source_to_modules_bi_analysis'),
    ]

    operations = [
        migrations.RunPython(remove_filemanager_menu, migrations.RunPython.noop),
    ]
