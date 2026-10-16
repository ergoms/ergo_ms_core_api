import uuid

import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    initial = True

    dependencies = []

    operations = [
        migrations.CreateModel(
            name='Person',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('public_id', models.UUIDField(db_index=True, default=uuid.uuid4, editable=False, unique=True)),
                ('user_public_id', models.UUIDField(blank=True, null=True, unique=True, verbose_name='Публичный идентификатор учётной записи')),
                ('last_name', models.CharField(blank=True, default='', max_length=150, verbose_name='Фамилия')),
                ('first_name', models.CharField(blank=True, default='', max_length=150, verbose_name='Имя')),
                ('middle_name', models.CharField(blank=True, default='', max_length=150, verbose_name='Отчество')),
                ('birth_date', models.DateField(blank=True, null=True, verbose_name='Дата рождения')),
                ('created_at', models.DateTimeField(auto_now_add=True, verbose_name='Создана')),
                ('updated_at', models.DateTimeField(auto_now=True, verbose_name='Обновлена')),
            ],
            options={
                'verbose_name': 'Карточка человека',
                'verbose_name_plural': 'Карточки людей',
                'db_table': 'core_person',
                'indexes': [models.Index(fields=['last_name', 'first_name'], name='core_person_name_idx')],
            },
        ),
        migrations.CreateModel(
            name='PersonAlias',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('loser_public_id', models.UUIDField(unique=True, verbose_name='Публичный идентификатор поглощённой карточки')),
                ('merged_at', models.DateTimeField(auto_now_add=True, verbose_name='Слита')),
                ('survivor', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='absorbed_aliases', to='core_persons.person', verbose_name='Выжившая карточка')),
            ],
            options={
                'verbose_name': 'Псевдоним карточки человека',
                'verbose_name_plural': 'Псевдонимы карточек людей',
                'db_table': 'core_person_alias',
            },
        ),
    ]
