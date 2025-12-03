# Generated manually for safely removing middle_name field from UserProfile

from django.db import migrations


def remove_middle_name_field_safe(apps, schema_editor):
    """
    Безопасно удаляет поле middle_name из UserProfile, если оно существует.
    Если поля нет - ничего не делает.
    Кроссплатформенное решение для SQLite и PostgreSQL.
    """
    from django.db import connection
    
    vendor = connection.vendor
    table_name = 'cms_adp_userprofile'
    column_name = 'middle_name'
    field_exists = False
    
    with connection.cursor() as cursor:
        # Проверяем существование колонки в зависимости от типа БД
        if vendor == 'sqlite':
            # Для SQLite используем PRAGMA table_info
            # PRAGMA не поддерживает параметризованные запросы, но имя таблицы контролируется нами
            cursor.execute(f'PRAGMA table_info("{table_name}")')
            columns = cursor.fetchall()
            # В PRAGMA table_info структура: (cid, name, type, notnull, default_value, pk)
            field_exists = any(col[1] == column_name for col in columns)
        elif vendor == 'postgresql':
            # Для PostgreSQL используем information_schema
            cursor.execute("""
                SELECT EXISTS (
                    SELECT 1 
                    FROM information_schema.columns 
                    WHERE table_schema = 'public' 
                    AND table_name = %s
                    AND column_name = %s
                )
            """, [table_name, column_name])
            field_exists = cursor.fetchone()[0]
        else:
            # Для других БД пытаемся использовать DROP COLUMN IF EXISTS
            # (большинство современных БД поддерживают это)
            try:
                cursor.execute(f"ALTER TABLE {table_name} DROP COLUMN IF EXISTS {column_name}")
                field_exists = True  # Предполагаем, что поле могло существовать
            except Exception:
                field_exists = False
        
        if field_exists:
            # Поле существует - удаляем его
            try:
                # Используем DROP COLUMN для разных БД
                if vendor == 'sqlite':
                    # SQLite 3.35.0+ поддерживает DROP COLUMN
                    # Для старых версий будет ошибка, но это не критично
                    cursor.execute(f'ALTER TABLE "{table_name}" DROP COLUMN "{column_name}"')
                else:
                    # PostgreSQL и другие БД - используем IF EXISTS
                    cursor.execute(f'ALTER TABLE "{table_name}" DROP COLUMN IF EXISTS "{column_name}"')
                print(f"[INFO] Поле {column_name} удалено из таблицы {table_name}.")
            except Exception as e:
                # Если не удалось удалить (старая версия SQLite или поле уже удалено)
                print(f"[INFO] Не удалось удалить поле {column_name}: {e}. Возможно, поле уже не существует или используется старая версия SQLite.")
        else:
            print(f"[INFO] Поле {column_name} не существует в таблице {table_name}. Пропускаем удаление.")


def add_middle_name_field_back(apps, schema_editor):
    """
    Обратная миграция - добавляет поле middle_name обратно, если его нет.
    Кроссплатформенное решение для SQLite и PostgreSQL.
    """
    from django.db import connection
    
    vendor = connection.vendor
    table_name = 'cms_adp_userprofile'
    column_name = 'middle_name'
    field_exists = False
    
    with connection.cursor() as cursor:
        # Проверяем существование колонки в зависимости от типа БД
        if vendor == 'sqlite':
            # Для SQLite используем PRAGMA table_info
            # PRAGMA не поддерживает параметризованные запросы, но имя таблицы контролируется нами
            cursor.execute(f'PRAGMA table_info("{table_name}")')
            columns = cursor.fetchall()
            field_exists = any(col[1] == column_name for col in columns)
        elif vendor == 'postgresql':
            # Для PostgreSQL используем information_schema
            cursor.execute("""
                SELECT EXISTS (
                    SELECT 1 
                    FROM information_schema.columns 
                    WHERE table_schema = 'public' 
                    AND table_name = %s
                    AND column_name = %s
                )
            """, [table_name, column_name])
            field_exists = cursor.fetchone()[0]
        else:
            # Для других БД пытаемся добавить колонку (будет ошибка, если уже существует)
            field_exists = False
        
        if not field_exists:
            # Поле не существует - добавляем его обратно
            try:
                # Все БД поддерживают ADD COLUMN
                cursor.execute(f"""
                    ALTER TABLE "{table_name}" 
                    ADD COLUMN "{column_name}" VARCHAR(150) NULL;
                """)
                print(f"[INFO] Поле {column_name} добавлено обратно в таблицу {table_name}.")
            except Exception as e:
                # Поле уже существует или произошла ошибка
                print(f"[INFO] Не удалось добавить поле {column_name}: {e}")
        else:
            print(f"[INFO] Поле {column_name} уже существует в таблице {table_name}. Пропускаем добавление.")


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

