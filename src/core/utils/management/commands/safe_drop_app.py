"""Команда для безопасного удаления приложения Django."""

from django.core.management.base import BaseCommand

from .safe_drop_app_analysis import SafeDropAppAnalysisMixin
from .safe_drop_app_deletion import SafeDropAppDeletionMixin


class Command(SafeDropAppDeletionMixin, SafeDropAppAnalysisMixin, BaseCommand):
    help = SafeDropAppAnalysisMixin.help
