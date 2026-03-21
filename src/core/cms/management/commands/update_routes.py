import os
import json

from django.core.management.base import BaseCommand, CommandError

from src.core.cms.models import CMSPage
from src.core.cms.scripts import extract_paths_from_routes_config


class Command(BaseCommand):
    help = 'Обновляет роуты в базе данных на основе routes.js'

    def add_arguments(self, parser):
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Показать изменения без фактического обновления БД',
        )
        parser.add_argument(
            '--verbose',
            action='store_true', 
            help='Показать детальную информацию о процессе',
        )

    def handle(self, *args, **options):
        self.dry_run = options['dry_run']
        self.verbose = options['verbose']
        
        self.stdout.write(
            self.style.SUCCESS('🚀 Начинаю обновление роутов...')
        )

        try:
            # Извлекаем пути из routes.js используя функцию из scripts.py
            paths_from_config = extract_paths_from_routes_config()
            
            if self.verbose:
                self.stdout.write(f"📋 Найдено {len(paths_from_config)} путей в routes.js")
            
            # Получаем текущие пути из БД
            existing_paths = set(CMSPage.objects.values_list('path', flat=True))
            
            if self.verbose:
                self.stdout.write(f"🗄️  Найдено {len(existing_paths)} путей в БД")
            
            # Определяем изменения
            paths_to_add = paths_from_config - existing_paths
            paths_to_remove = existing_paths - paths_from_config
            
            # Показываем статистику
            self.show_statistics(paths_to_add, paths_to_remove, paths_from_config & existing_paths)
            
            if not self.dry_run:
                # Применяем изменения
                self.apply_changes(paths_to_add, paths_to_remove)
                self.stdout.write(
                    self.style.SUCCESS('✅ Обновление роутов завершено успешно!')
                )
            else:
                self.stdout.write(
                    self.style.WARNING('🔍 Это был пробный запуск. Изменения не применены.')
                )
                
        except Exception as e:
            raise CommandError(f'❌ Ошибка при обновлении роутов: {str(e)}')

    def show_statistics(self, paths_to_add, paths_to_remove, unchanged_paths):
        """Показывает статистику изменений"""
        self.stdout.write("\n📊 Статистика изменений:")
        self.stdout.write(f"  ➕ Новых путей: {len(paths_to_add)}")
        self.stdout.write(f"  ➖ Путей к удалению: {len(paths_to_remove)}")  
        self.stdout.write(f"  ✅ Без изменений: {len(unchanged_paths)}")
        
        if self.verbose and paths_to_add:
            self.stdout.write("\n➕ Новые пути:")
            for path in sorted(paths_to_add):
                self.stdout.write(f"   + {path}")
                
        if self.verbose and paths_to_remove:
            self.stdout.write("\n➖ Пути к удалению:")
            for path in sorted(paths_to_remove):
                self.stdout.write(f"   - {path}")

    def apply_changes(self, paths_to_add, paths_to_remove):
        """Применяет изменения к базе данных"""
        
        # Добавляем новые пути
        if paths_to_add:
            new_pages = [CMSPage(path=path) for path in paths_to_add]
            CMSPage.objects.bulk_create(new_pages)
            self.stdout.write(
                self.style.SUCCESS(f"➕ Добавлено {len(paths_to_add)} новых путей")
            )
        
        # Удаляем старые пути
        if paths_to_remove:
            deleted_count, _ = CMSPage.objects.filter(path__in=paths_to_remove).delete()
            self.stdout.write(
                self.style.SUCCESS(f"➖ Удалено {deleted_count} устаревших путей")
            ) 