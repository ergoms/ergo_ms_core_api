# Generated manually for TechnologicalProcessDocument model

import django.db.models.deletion
import uuid
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("ai_assistant", "0003_knowledgedocument_knowledgechunk_and_more"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name="TechnologicalProcessDocument",
            fields=[
                (
                    "id",
                    models.UUIDField(
                        default=uuid.uuid4,
                        editable=False,
                        primary_key=True,
                        serialize=False,
                    ),
                ),
                (
                    "title",
                    models.CharField(
                        help_text="Название документа техпроцесса", max_length=500
                    ),
                ),
                (
                    "file",
                    models.FileField(
                        help_text="Оригинальный файл техпроцесса (DOCX)",
                        upload_to="tp_documents/",
                    ),
                ),
                (
                    "file_type",
                    models.CharField(
                        default="docx",
                        help_text="Тип файла (обычно docx)",
                        max_length=50,
                    ),
                ),
                (
                    "markdown_content",
                    models.TextField(
                        help_text="Конвертированный Markdown контент документа"
                    ),
                ),
                (
                    "metadata",
                    models.JSONField(
                        blank=True,
                        default=dict,
                        help_text="Дополнительные метаданные документа",
                    ),
                ),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                (
                    "user",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="tp_documents",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
            ],
            options={
                "ordering": ["-created_at"],
                "verbose_name": "Документ техпроцесса",
                "verbose_name_plural": "Документы техпроцессов",
            },
        ),
        migrations.AddIndex(
            model_name="technologicalprocessdocument",
            index=models.Index(
                fields=["user", "-created_at"],
                name="ai_assistan_user_id_abc123_idx",
            ),
        ),
    ]
