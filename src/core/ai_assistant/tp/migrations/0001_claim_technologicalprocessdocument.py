# Claim existing ai_assistant_technologicalprocessdocument table by tp app (state only)

import uuid
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    initial = True
    dependencies = [
        ("ai_assistant", "0006_remove_technologicalprocessdocument_state"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    state_operations = [
        migrations.CreateModel(
            name="TechnologicalProcessDocument",
            fields=[
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ("title", models.CharField(help_text="Название документа техпроцесса", max_length=500)),
                ("file_type", models.CharField(default="docx", help_text="Тип файла (обычно docx)", max_length=50)),
                ("markdown_content", models.TextField(help_text="Конвертированный Markdown контент документа")),
                ("metadata", models.JSONField(blank=True, default=dict, help_text="Дополнительные метаданные документа")),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                (
                    "file",
                    models.FileField(
                        help_text="Оригинальный файл техпроцесса (DOCX)",
                        upload_to="tp_documents/%s.docx",
                    ),
                ),
                (
                    "session",
                    models.ForeignKey(
                        blank=True,
                        help_text="Сессия чата, к которой привязан документ",
                        null=True,
                        on_delete=models.CASCADE,
                        related_name="tp_documents",
                        to="ai_assistant.chatsession",
                    ),
                ),
                (
                    "user",
                    models.ForeignKey(
                        on_delete=models.CASCADE,
                        related_name="tp_documents",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
            ],
            options={
                "db_table": "ai_assistant_technologicalprocessdocument",
                "ordering": ["-created_at"],
                "verbose_name": "Документ техпроцесса",
                "verbose_name_plural": "Документы техпроцессов",
            },
        ),
        migrations.AddIndex(
            model_name="technologicalprocessdocument",
            index=models.Index(fields=["user", "-created_at"], name="ai_assistan_user_id_abc123_idx"),
        ),
        migrations.AddIndex(
            model_name="technologicalprocessdocument",
            index=models.Index(fields=["session", "-created_at"], name="ai_assistan_session_abc123_idx"),
        ),
    ]

    operations = [
        migrations.SeparateDatabaseAndState(state_operations=state_operations, database_operations=[]),
    ]
