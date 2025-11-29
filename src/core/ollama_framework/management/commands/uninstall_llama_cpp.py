"""
Django команда для удаления llama.cpp из системы
"""

import shutil
from pathlib import Path

from django.core.management.base import BaseCommand, CommandError
from django.conf import settings


class Command(BaseCommand):
    help = 'Удаляет llama.cpp из virtual_env/packages/llama_cpp'
    
    def add_arguments(self, parser):
        parser.add_argument(
            '--remove-models',
            action='store_true',
            help='Также удалить все модели GGUF из virtual_env/packages/models',
        )
    
    def handle(self, *args, **options):
        remove_models = options.get('remove_models', False)
        
        # Определяем пути
        packages_path = Path(settings.PACKAGES_PATH)
        llama_cpp_path = packages_path / 'llama_cpp'
        models_path = packages_path / 'models'
        
        # Удаляем llama.cpp
        if llama_cpp_path.exists():
            self.stdout.write(f'Удаление llama.cpp из {llama_cpp_path}...')
            try:
                shutil.rmtree(llama_cpp_path)
                self.stdout.write(self.style.SUCCESS('llama.cpp удален'))
            except Exception as e:
                raise CommandError(f'Ошибка при удалении llama.cpp: {e}')
        else:
            self.stdout.write(self.style.WARNING(
                'llama.cpp не найден в virtual_env/packages/llama_cpp'
            ))
        
        # Удаляем модели GGUF, если запрошено
        if remove_models and models_path.exists():
            self.stdout.write(f'Удаление моделей GGUF из {models_path}...')
            try:
                # Удаляем только GGUF файлы
                gguf_files = list(models_path.glob('**/*.gguf'))
                for gguf_file in gguf_files:
                    gguf_file.unlink()
                    self.stdout.write(f'  Удален: {gguf_file.name}')
                
                if gguf_files:
                    self.stdout.write(self.style.SUCCESS(
                        f'Удалено {len(gguf_files)} GGUF моделей'
                    ))
                else:
                    self.stdout.write(self.style.WARNING('GGUF модели не найдены'))
            except Exception as e:
                raise CommandError(f'Ошибка при удалении моделей: {e}')
        elif remove_models:
            self.stdout.write(self.style.WARNING('Папка с моделями не найдена'))
        
        self.stdout.write(self.style.SUCCESS('\nУдаление завершено!'))

