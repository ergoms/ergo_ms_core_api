from django.db import models

from src.core.utils.base import PublicIdMixin


class Person(PublicIdMixin, models.Model):
    """Личность человека. Учётка привязана необязательно и может исчезнуть раньше карточки."""

    user_public_id = models.UUIDField(
        null=True,
        blank=True,
        unique=True,
        verbose_name='Публичный идентификатор учётной записи',
    )
    last_name = models.CharField(max_length=150, blank=True, default='', verbose_name='Фамилия')
    first_name = models.CharField(max_length=150, blank=True, default='', verbose_name='Имя')
    middle_name = models.CharField(max_length=150, blank=True, default='', verbose_name='Отчество')
    birth_date = models.DateField(null=True, blank=True, verbose_name='Дата рождения')
    created_at = models.DateTimeField(auto_now_add=True, verbose_name='Создана')
    updated_at = models.DateTimeField(auto_now=True, verbose_name='Обновлена')

    class Meta:
        db_table = 'core_person'
        verbose_name = 'Карточка человека'
        verbose_name_plural = 'Карточки людей'
        indexes = [
            models.Index(fields=['last_name', 'first_name'], name='core_person_name_idx'),
        ]

    def __str__(self):
        name = ' '.join(
            part for part in (self.last_name, self.first_name, self.middle_name) if part
        ).strip()
        return name or f'Person {self.public_id}'


class PersonAlias(models.Model):
    """Идентификатор поглощённой при слиянии карточки указывает на выжившую."""

    loser_public_id = models.UUIDField(unique=True, verbose_name='Публичный идентификатор поглощённой карточки')
    survivor = models.ForeignKey(
        Person,
        on_delete=models.CASCADE,
        related_name='absorbed_aliases',
        verbose_name='Выжившая карточка',
    )
    merged_at = models.DateTimeField(auto_now_add=True, verbose_name='Слита')

    class Meta:
        db_table = 'core_person_alias'
        verbose_name = 'Псевдоним карточки человека'
        verbose_name_plural = 'Псевдонимы карточек людей'

    def __str__(self):
        return f'{self.loser_public_id} -> {self.survivor_id}'
