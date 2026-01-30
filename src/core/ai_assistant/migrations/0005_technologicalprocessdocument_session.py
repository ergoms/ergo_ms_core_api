# Generated manually for adding session field to TechnologicalProcessDocument

import django.db.models.deletion
import uuid
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("ai_assistant", "0004_technologicalprocessdocument"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.AddField(
            model_name="technologicalprocessdocument",
            name="session",
            field=models.ForeignKey(
                help_text="Сессия чата, к которой привязан документ",
                null=True,
                blank=True,
                on_delete=django.db.models.deletion.CASCADE,
                related_name="tp_documents",
                to="ai_assistant.chatsession",
            ),
        ),
        migrations.AddIndex(
            model_name="technologicalprocessdocument",
            index=models.Index(
                fields=["session", "-created_at"],
                name="ai_assistan_session_abc123_idx",
            ),
        ),
    ]
