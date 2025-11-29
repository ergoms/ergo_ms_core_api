"""
Django команда для установки llama.cpp в систему
"""

import os
import subprocess
import platform
import shutil
import zipfile
import tarfile
from pathlib import Path
from urllib.request import urlretrieve, urlopen
import json

from django.core.management.base import BaseCommand, CommandError
from django.conf import settings


class Command(BaseCommand):
    help = 'Устанавливает llama.cpp в virtual_env/packages/llama_cpp'
    
    # Версия llama.cpp для установки (используем последний релиз)
    GITHUB_API_URL = "https://api.github.com/repos/ggerganov/llama.cpp/releases/latest"
    
    def add_arguments(self, parser):
        parser.add_argument(
            '--force',
            action='store_true',
            help='Переустановить llama.cpp, даже если он уже установлен',
        )
        parser.add_argument(
            '--cuda',
            action='store_true',
            help='Установить версию с поддержкой CUDA (для NVIDIA GPU)',
        )
        parser.add_argument(
            '--vulkan',
            action='store_true',
            help='Установить версию с поддержкой Vulkan (для AMD/Intel GPU)',
        )
        parser.add_argument(
            '--cpu',
            action='store_true',
            help='Установить версию только для CPU (без GPU ускорения)',
        )
    
    def handle(self, *args, **options):
        force = options.get('force', False)
        use_cuda = options.get('cuda', False)
        use_vulkan = options.get('vulkan', False)
        use_cpu = options.get('cpu', False)
        
        # Если не указан конкретный бэкенд, пытаемся определить автоматически
        if not any([use_cuda, use_vulkan, use_cpu]):
            use_cuda, use_vulkan = self._detect_gpu()
            if not use_cuda and not use_vulkan:
                use_cpu = True
        
        # Определяем пути
        packages_path = Path(settings.PACKAGES_PATH)
        llama_cpp_path = packages_path / 'llama_cpp'
        models_path = packages_path / 'models'
        
        # Проверяем, установлен ли уже llama.cpp
        if llama_cpp_path.exists() and not force:
            self.stdout.write(self.style.WARNING(
                f'llama.cpp уже установлен в {llama_cpp_path}\n'
                'Используйте --force для переустановки'
            ))
            return
        
        # Создаем директории
        packages_path.mkdir(parents=True, exist_ok=True)
        models_path.mkdir(parents=True, exist_ok=True)
        
        if force and llama_cpp_path.exists():
            self.stdout.write('Удаление старой установки...')
            shutil.rmtree(llama_cpp_path, ignore_errors=True)
        
        self.stdout.write('Установка llama.cpp...')
        
        # Определяем платформу
        system = platform.system().lower()
        machine = platform.machine().lower()
        
        try:
            if system == 'windows':
                self._install_windows(llama_cpp_path, models_path, machine, use_cuda, use_vulkan)
            elif system == 'linux':
                self._install_linux(llama_cpp_path, models_path, machine, use_cuda, use_vulkan)
            else:
                raise CommandError(f'Неподдерживаемая ОС: {system}')
        except Exception as e:
            raise CommandError(f'Ошибка при установке llama.cpp: {e}')
        
        # Выводим инструкции
        backend = "CUDA" if use_cuda else ("Vulkan" if use_vulkan else "CPU")
        models_path_str = str(models_path.absolute())
        llama_cpp_path_str = str(llama_cpp_path.absolute())
        
        self.stdout.write(self.style.SUCCESS(
            f'\nllama.cpp установлен!\n\n'
            f'Путь к llama.cpp: {llama_cpp_path_str}\n'
            f'Путь к моделям: {models_path_str}\n'
            f'GPU Backend: {backend}\n\n'
            f'Настройте переменные окружения в .env:\n\n'
            f'# Переключение на llama.cpp\n'
            f'LLM_PROVIDER=llama_cpp\n\n'
            f'# URL сервера llama.cpp (по умолчанию)\n'
            f'LLAMA_CPP_BASE_URL=http://localhost:8080\n\n'
            f'# Количество слоев на GPU (для CUDA/Vulkan)\n'
            f'LLAMA_CPP_GPU_LAYERS=35\n\n'
            f'# Количество потоков CPU\n'
            f'LLAMA_CPP_THREADS=8\n\n'
            f'# Размер контекста\n'
            f'LLAMA_CPP_CONTEXT_SIZE=4096\n\n'
            f'Запуск сервера:\n'
            f'  ergoms start-llama-cpp --model path/to/model.gguf\n'
        ))
    
    def _detect_gpu(self) -> tuple:
        """Определяет доступный GPU"""
        use_cuda = False
        use_vulkan = False
        
        # Проверяем NVIDIA GPU через nvidia-smi
        try:
            result = subprocess.run(
                ['nvidia-smi', '--query-gpu=name', '--format=csv,noheader'],
                capture_output=True,
                text=True,
                timeout=5
            )
            if result.returncode == 0 and result.stdout.strip():
                self.stdout.write(f'Обнаружен NVIDIA GPU: {result.stdout.strip()}')
                use_cuda = True
        except (FileNotFoundError, subprocess.TimeoutExpired):
            pass
        
        # Если нет CUDA, проверяем Vulkan
        if not use_cuda:
            try:
                # На Windows проверяем через vulkaninfo
                if platform.system().lower() == 'windows':
                    result = subprocess.run(
                        ['vulkaninfo', '--summary'],
                        capture_output=True,
                        text=True,
                        timeout=5
                    )
                    if result.returncode == 0:
                        self.stdout.write('Обнаружена поддержка Vulkan')
                        use_vulkan = True
            except (FileNotFoundError, subprocess.TimeoutExpired):
                pass
        
        if not use_cuda and not use_vulkan:
            self.stdout.write(self.style.WARNING(
                'GPU не обнаружен, используется CPU версия'
            ))
        
        return use_cuda, use_vulkan
    
    def _get_latest_release_info(self) -> dict:
        """Получает информацию о последнем релизе llama.cpp"""
        try:
            with urlopen(self.GITHUB_API_URL, timeout=30) as response:
                return json.loads(response.read().decode('utf-8'))
        except Exception as e:
            raise CommandError(f'Не удалось получить информацию о релизах: {e}')
    
    def _find_asset(self, assets: list, keywords: list, exclude_keywords: list = None) -> dict:
        """Находит подходящий asset по ключевым словам"""
        exclude_keywords = exclude_keywords or []
        for asset in assets:
            name = asset['name'].lower()
            if all(kw in name for kw in keywords):
                if not any(ex in name for ex in exclude_keywords):
                    return asset
        return None
    
    def _install_windows(self, llama_cpp_path: Path, models_path: Path, machine: str, use_cuda: bool, use_vulkan: bool):
        """Установка llama.cpp на Windows"""
        self.stdout.write('Получение информации о последнем релизе...')
        release_info = self._get_latest_release_info()
        assets = release_info.get('assets', [])
        
        # Определяем архитектуру
        if '64' in machine or 'amd64' in machine or 'x86_64' in machine:
            arch = 'x64'
        else:
            arch = 'x64'  # Fallback to x64
        
        # Ищем подходящий asset
        asset = None
        exclude = ['rocm', 'sycl', 'kompute', 'noavx', 'arm64']
        
        if use_cuda:
            # Ищем CUDA версию (cu12 или cu11)
            for cuda_ver in ['cu12', 'cu11']:
                asset = self._find_asset(
                    assets, 
                    ['win', cuda_ver, 'x64', '.zip'],
                    exclude
                )
                if asset:
                    break
        elif use_vulkan:
            asset = self._find_asset(
                assets,
                ['win', 'vulkan', 'x64', '.zip'],
                exclude
            )
        
        # Если не нашли GPU версию, берём CPU
        if not asset:
            asset = self._find_asset(
                assets,
                ['win', 'x64', '.zip'],
                exclude + ['cuda', 'cu12', 'cu11', 'vulkan']
            )
        
        if not asset:
            # Fallback - берём первый Windows asset
            for a in assets:
                if 'win' in a['name'].lower() and a['name'].endswith('.zip'):
                    asset = a
                    break
        
        if not asset:
            raise CommandError('Не найден подходящий релиз для Windows')
        
        download_url = asset['browser_download_url']
        self.stdout.write(f'Скачивание: {asset["name"]}...')
        
        # Скачиваем архив
        temp_dir = Path(os.environ.get('TEMP', '/tmp'))
        archive_path = temp_dir / asset['name']
        urlretrieve(download_url, archive_path)
        
        # Распаковываем
        self.stdout.write('Распаковка...')
        llama_cpp_path.mkdir(parents=True, exist_ok=True)
        
        with zipfile.ZipFile(archive_path, 'r') as zip_ref:
            zip_ref.extractall(llama_cpp_path)
        
        # Удаляем архив
        archive_path.unlink()
        
        # Проверяем наличие llama-server.exe
        server_exe = self._find_server_exe(llama_cpp_path)
        if server_exe:
            self.stdout.write(self.style.SUCCESS(f'llama-server найден: {server_exe}'))
        else:
            self.stdout.write(self.style.WARNING(
                'llama-server.exe не найден. Возможно, структура архива изменилась.'
            ))
    
    def _install_linux(self, llama_cpp_path: Path, models_path: Path, machine: str, use_cuda: bool, use_vulkan: bool):
        """Установка llama.cpp на Linux"""
        self.stdout.write('Получение информации о последнем релизе...')
        release_info = self._get_latest_release_info()
        assets = release_info.get('assets', [])
        
        # Определяем архитектуру
        if 'x86_64' in machine or 'amd64' in machine:
            arch = 'x64'
        elif 'aarch64' in machine or 'arm64' in machine:
            arch = 'aarch64'
        else:
            arch = 'x64'  # Fallback
        
        # Ищем подходящий asset
        asset = None
        exclude = ['rocm', 'sycl', 'kompute', 'win', 'macos']
        
        if use_cuda:
            for cuda_ver in ['cu12', 'cu11']:
                asset = self._find_asset(
                    assets,
                    ['linux', cuda_ver, '.tar.gz'],
                    exclude
                )
                if asset:
                    break
        elif use_vulkan:
            asset = self._find_asset(
                assets,
                ['linux', 'vulkan', '.tar.gz'],
                exclude
            )
        
        # Если не нашли GPU версию, берём CPU
        if not asset:
            asset = self._find_asset(
                assets,
                ['linux', arch, '.tar.gz'],
                exclude + ['cuda', 'cu12', 'cu11', 'vulkan']
            )
        
        if not asset:
            # Fallback
            for a in assets:
                if 'linux' in a['name'].lower() and a['name'].endswith('.tar.gz'):
                    asset = a
                    break
        
        if not asset:
            raise CommandError('Не найден подходящий релиз для Linux')
        
        download_url = asset['browser_download_url']
        self.stdout.write(f'Скачивание: {asset["name"]}...')
        
        # Скачиваем архив
        temp_dir = Path('/tmp')
        archive_path = temp_dir / asset['name']
        urlretrieve(download_url, archive_path)
        
        # Распаковываем
        self.stdout.write('Распаковка...')
        llama_cpp_path.mkdir(parents=True, exist_ok=True)
        
        with tarfile.open(archive_path, 'r:gz') as tar_ref:
            tar_ref.extractall(llama_cpp_path)
        
        # Удаляем архив
        archive_path.unlink()
        
        # Делаем исполняемые файлы
        for exe in llama_cpp_path.rglob('*'):
            if exe.is_file() and exe.suffix == '':
                os.chmod(exe, 0o755)
        
        # Проверяем наличие llama-server
        server_exe = self._find_server_exe(llama_cpp_path)
        if server_exe:
            self.stdout.write(self.style.SUCCESS(f'llama-server найден: {server_exe}'))
        else:
            self.stdout.write(self.style.WARNING(
                'llama-server не найден. Возможно, структура архива изменилась.'
            ))
    
    def _find_server_exe(self, llama_cpp_path: Path) -> Path:
        """Ищет исполняемый файл llama-server"""
        patterns = ['llama-server', 'llama-server.exe', 'server', 'server.exe']
        
        for pattern in patterns:
            for path in llama_cpp_path.rglob(pattern):
                if path.is_file():
                    return path
        
        return None

