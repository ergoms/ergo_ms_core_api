"""
Django команда для удаления Ollama из системы
"""

import shutil
from pathlib import Path

from django.core.management.base import BaseCommand, CommandError
from django.conf import settings


class Command(BaseCommand):
    help = 'Удаляет Ollama из virtual_env/packages/ollama'
    
    def add_arguments(self, parser):
        parser.add_argument(
            '--remove-models',
            action='store_true',
            help='Также удалить все модели из virtual_env/packages/models',
        )
    
    def handle(self, *args, **options):
        remove_models = options.get('remove_models', False)
        
        # Определяем пути
        packages_path = Path(settings.PACKAGES_PATH)
        ollama_path = packages_path / 'ollama'
        models_path = packages_path / 'models'
        
        # Удаляем Ollama
        if ollama_path.exists():
            self.stdout.write(f'🗑️  Удаление Ollama из {ollama_path}...')
            try:
                shutil.rmtree(ollama_path)
                self.stdout.write(self.style.SUCCESS('✅ Ollama удален'))
            except Exception as e:
                raise CommandError(f'❌ Ошибка при удалении Ollama: {e}')
        else:
            self.stdout.write(self.style.WARNING('⚠️  Ollama не найден в virtual_env/packages/ollama'))
        
        # Удаляем модели, если запрошено
        if remove_models and models_path.exists():
            self.stdout.write(f'🗑️  Удаление моделей из {models_path}...')
            try:
                # Подсчитываем количество моделей
                model_count = len(list(models_path.iterdir()))
                shutil.rmtree(models_path)
                models_path.mkdir(parents=True, exist_ok=True)  # Создаем пустую директорию
                self.stdout.write(self.style.SUCCESS(f'✅ Удалено {model_count} моделей'))
            except Exception as e:
                raise CommandError(f'❌ Ошибка при удалении моделей: {e}')
        elif remove_models:
            self.stdout.write(self.style.WARNING('⚠️  Папка с моделями не найдена'))
        
        self.stdout.write(self.style.SUCCESS('\n✅ Удаление завершено!'))

