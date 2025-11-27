# Generated manually for safely removing middle_name field from UserProfile

from django.db import migrations


def remove_middle_name_field_safe(apps, schema_editor):
    """
    Безопасно удаляет поле middle_name из UserProfile, если оно существует.
    Если поля нет - ничего не делает.
    """
    from django.db import connection
    
    with connection.cursor() as cursor:
        # Проверяем, существует ли поле middle_name в таблице cms_adp_userprofile
        cursor.execute("""
            SELECT EXISTS (
                SELECT 1 
                FROM information_schema.columns 
                WHERE table_schema = 'public' 
                AND table_name = 'cms_adp_userprofile'
                AND column_name = 'middle_name'
            )
        """)
        field_exists = cursor.fetchone()[0]
        
        if field_exists:
            # Поле существует - удаляем его
            cursor.execute("ALTER TABLE cms_adp_userprofile DROP COLUMN IF EXISTS middle_name;")
            print("[INFO] Поле middle_name удалено из таблицы cms_adp_userprofile.")
        else:
            print("[INFO] Поле middle_name не существует в таблице cms_adp_userprofile. Пропускаем удаление.")


def add_middle_name_field_back(apps, schema_editor):
    """
    Обратная миграция - добавляет поле middle_name обратно, если его нет.
    """
    from django.db import connection
    
    with connection.cursor() as cursor:
        # Проверяем, существует ли поле
        cursor.execute("""
            SELECT EXISTS (
                SELECT 1 
                FROM information_schema.columns 
                WHERE table_schema = 'public' 
                AND table_name = 'cms_adp_userprofile'
                AND column_name = 'middle_name'
            )
        """)
        field_exists = cursor.fetchone()[0]
        
        if not field_exists:
            # Поле не существует - добавляем его обратно
            cursor.execute("""
                ALTER TABLE cms_adp_userprofile 
                ADD COLUMN middle_name VARCHAR(150) NULL;
            """)
            print("[INFO] Поле middle_name добавлено обратно в таблицу cms_adp_userprofile.")


class Migration(migrations.Migration):

    dependencies = [
        ('cms_adp', '0004_role_rolegroup_policy_modulepermission_userrole'),
    ]

    operations = [
        migrations.RunPython(
            remove_middle_name_field_safe,
            add_middle_name_field_back,
        ),
    ]

