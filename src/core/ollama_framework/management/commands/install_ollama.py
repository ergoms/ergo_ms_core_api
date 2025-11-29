"""
Django команда для установки Ollama в систему
"""

import os
import subprocess
import platform
import shutil
from pathlib import Path
from urllib.request import urlretrieve

from django.core.management.base import BaseCommand, CommandError
from django.conf import settings


class Command(BaseCommand):
    help = 'Устанавливает Ollama в virtual_env/packages/ollama'
    
    def add_arguments(self, parser):
        parser.add_argument(
            '--force',
            action='store_true',
            help='Переустановить Ollama, даже если он уже установлен',
        )
    
    def handle(self, *args, **options):
        force = options.get('force', False)
        
        # Определяем пути
        packages_path = Path(settings.PACKAGES_PATH)
        ollama_path = packages_path / 'ollama'
        models_path = packages_path / 'models'
        
        # Проверяем, установлен ли уже Ollama
        if ollama_path.exists() and not force:
            self.stdout.write(self.style.WARNING(
                f'🦙 Ollama уже установлен в {ollama_path}\n'
                'Используйте --force для переустановки'
            ))
            return
        
        # Создаем директории
        packages_path.mkdir(parents=True, exist_ok=True)
        models_path.mkdir(parents=True, exist_ok=True)
        
        if force and ollama_path.exists():
            self.stdout.write('🗑️  Удаление старой установки...')
            shutil.rmtree(ollama_path, ignore_errors=True)
        
        self.stdout.write('📥 Установка Ollama...')
        
        # Определяем платформу
        system = platform.system().lower()
        machine = platform.machine().lower()
        
        try:
            if system == 'windows':
                self._install_windows(ollama_path, models_path, machine)
            elif system == 'linux':
                self._install_linux(ollama_path, models_path, machine)
            else:
                raise CommandError(f'❌ Неподдерживаемая ОС: {system}')
        except Exception as e:
            raise CommandError(f'❌ Ошибка при установке Ollama: {e}')
        
        # Выводим инструкции по настройке
        models_path_str = str(models_path.absolute())
        self.stdout.write(self.style.SUCCESS(
            f'\n✅ Ollama установлен!\n\n'
            f'📁 Путь к Ollama: {ollama_path.absolute()}\n'
            f'📁 Путь к моделям: {models_path_str}\n\n'
            f'⚠️  ВАЖНО: Установите переменную окружения:\n'
            f'   OLLAMA_MODELS={models_path_str}\n\n'
            f'Для Windows (PowerShell):\n'
            f'   [System.Environment]::SetEnvironmentVariable("OLLAMA_MODELS", "{models_path_str}", "User")\n\n'
            f'Для Linux (Bash):\n'
            f'   echo \'export OLLAMA_MODELS="{models_path_str}"\' >> ~/.bashrc\n'
            f'   source ~/.bashrc\n'
        ))
    
    def _install_windows(self, ollama_path: Path, models_path: Path, machine: str):
        """Установка Ollama на Windows"""
        self.stdout.write('📥 Установка Ollama через официальный установщик...')
        
        # Скачиваем установщик
        download_path = Path.home() / 'AppData' / 'Local' / 'Temp' / 'OllamaSetup.exe'
        url = 'https://github.com/ollama/ollama/releases/latest/download/OllamaSetup.exe'
        
        if '64' not in machine and 'x86_64' not in machine and 'amd64' not in machine:
            raise CommandError('❌ Неподдерживаемая архитектура Windows')
        
        self.stdout.write(f'📥 Скачивание из {url}...')
        download_path.parent.mkdir(parents=True, exist_ok=True)
        urlretrieve(url, download_path)
        
        # Запускаем установщик в тихом режиме
        self.stdout.write('⚙️  Запуск установщика (может потребоваться подтверждение UAC)...')
        result = subprocess.run(
            [str(download_path), '/S'],
            check=False,
            capture_output=True,
            text=True
        )
        
        # Удаляем установщик
        if download_path.exists():
            download_path.unlink()
        
        if result.returncode != 0:
            self.stdout.write(self.style.WARNING(
                f'⚠️  Установщик завершился с кодом {result.returncode}'
            ))
        
        # Ищем установленный Ollama
        possible_paths = [
            Path(os.environ.get('ProgramFiles', '')) / 'Ollama' / 'ollama.exe',
            Path(os.environ.get('ProgramFiles(x86)', '')) / 'Ollama' / 'ollama.exe',
            Path.home() / 'AppData' / 'Local' / 'Programs' / 'Ollama' / 'ollama.exe',
        ]
        
        ollama_exe = None
        for path in possible_paths:
            if path.exists():
                ollama_exe = path
                break
        
        if ollama_exe:
            ollama_path.mkdir(parents=True, exist_ok=True)
            target_exe = ollama_path / 'ollama.exe'
            shutil.copy2(ollama_exe, target_exe)
            self.stdout.write(self.style.SUCCESS(f'✅ Ollama скопирован в {target_exe}'))
        else:
            # Создаем обертку, которая использует системный ollama
            ollama_path.mkdir(parents=True, exist_ok=True)
            wrapper_script = ollama_path / 'ollama.bat'
            with open(wrapper_script, 'w', encoding='utf-8') as f:
                f.write('@echo off\n')
                f.write(f'set OLLAMA_MODELS={models_path.absolute()}\n')
                f.write('ollama %*\n')
            self.stdout.write(self.style.WARNING(
                '⚠️  Создан скрипт-обертка. Убедитесь, что ollama доступен в PATH.\n'
                '   Скрипт автоматически устанавливает OLLAMA_MODELS.'
            ))
    
    def _install_linux(self, ollama_path: Path, models_path: Path, machine: str):
        """Установка Ollama на Linux"""
        self.stdout.write('📥 Установка Ollama...')
        
        # Определяем URL для бинарника
        if 'x86_64' in machine or 'amd64' in machine:
            url = 'https://github.com/ollama/ollama/releases/latest/download/ollama-linux-amd64'
            exe_name = 'ollama'
        elif 'arm64' in machine or 'aarch64' in machine:
            url = 'https://github.com/ollama/ollama/releases/latest/download/ollama-linux-arm64'
            exe_name = 'ollama'
        else:
            raise CommandError(f'❌ Неподдерживаемая архитектура Linux: {machine}')
        
        # Скачиваем бинарник
        download_path = ollama_path.parent / exe_name
        self.stdout.write(f'📥 Скачивание из {url}...')
        ollama_path.parent.mkdir(parents=True, exist_ok=True)
        urlretrieve(url, download_path)
        
        # Копируем в packages/ollama
        ollama_path.mkdir(parents=True, exist_ok=True)
        target_exe = ollama_path / 'ollama'
        shutil.copy2(download_path, target_exe)
        os.chmod(target_exe, 0o755)
        
        # Удаляем временный файл
        if download_path.exists():
            download_path.unlink()
        
        self.stdout.write(self.style.SUCCESS(f'✅ Ollama установлен в {target_exe}'))
