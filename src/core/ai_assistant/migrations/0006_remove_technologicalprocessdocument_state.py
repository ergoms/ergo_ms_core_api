# Remove TechnologicalProcessDocument from ai_assistant state only (table stays for tp app)

from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ("ai_assistant", "0005_technologicalprocessdocument_session"),
    ]

    state_operations = [
        migrations.DeleteModel(name="TechnologicalProcessDocument"),
    ]

    operations = [
        migrations.SeparateDatabaseAndState(state_operations=state_operations, database_operations=[]),
    ]
