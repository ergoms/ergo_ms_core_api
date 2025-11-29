"""
Django команда для запуска llama.cpp сервера
"""

import os
import subprocess
import sys
import time
import platform
from pathlib import Path
from typing import Optional, List, Dict, Any

import psutil

from django.core.management.base import BaseCommand, CommandError
from django.conf import settings


class Command(BaseCommand):
    help = 'Запускает llama.cpp сервер'
    
    # Цвета для консоли
    CYAN = '\033[96m'
    GREEN = '\033[92m'
    YELLOW = '\033[93m'
    MAGENTA = '\033[95m'
    RESET = '\033[0m'
    BOLD = '\033[1m'
    
    def add_arguments(self, parser):
        parser.add_argument(
            '--model', '-m',
            type=str,
            help='Путь к модели GGUF (относительно virtual_env/packages/models или абсолютный путь)'
        )
        parser.add_argument(
            '--host',
            type=str,
            default=os.getenv('LLAMA_CPP_HOST', '127.0.0.1'),
            help='Хост для сервера (по умолчанию: 127.0.0.1)'
        )
        parser.add_argument(
            '--port', '-p',
            type=int,
            default=int(os.getenv('LLAMA_CPP_PORT', '8080')),
            help='Порт для сервера (по умолчанию: 8080)'
        )
        parser.add_argument(
            '--gpu-layers', '-ngl',
            type=int,
            default=int(os.getenv('LLAMA_CPP_GPU_LAYERS', '35')),
            help='Количество слоев на GPU (по умолчанию: 35, 0 для CPU)'
        )
        parser.add_argument(
            '--threads', '-t',
            type=int,
            default=int(os.getenv('LLAMA_CPP_THREADS', '8')),
            help='Количество потоков CPU (по умолчанию: 8)'
        )
        parser.add_argument(
            '--context-size', '-c',
            type=int,
            default=int(os.getenv('LLAMA_CPP_CONTEXT_SIZE', '4096')),
            help='Размер контекста (по умолчанию: 4096)'
        )
        parser.add_argument(
            '--batch-size', '-b',
            type=int,
            default=int(os.getenv('LLAMA_CPP_BATCH_SIZE', '512')),
            help='Размер батча (по умолчанию: 512)'
        )
        parser.add_argument(
            '--parallel', '-np',
            type=int,
            default=int(os.getenv('LLAMA_CPP_PARALLEL', '1')),
            help='Количество параллельных запросов (по умолчанию: 1)'
        )
        parser.add_argument(
            '--flash-attn', '-fa',
            action='store_true',
            default=os.getenv('LLAMA_CPP_FLASH_ATTN', 'false').lower() == 'true',
            help='Включить Flash Attention (для CUDA)'
        )
        parser.add_argument(
            '--mlock',
            action='store_true',
            default=os.getenv('LLAMA_CPP_MLOCK', 'false').lower() == 'true',
            help='Заблокировать модель в RAM (предотвращает swap)'
        )
        parser.add_argument(
            '--foreground', '-f',
            action='store_true',
            help='Запустить в foreground режиме (не в фоне)'
        )
    
    def handle(self, *args, **options):
        # Проверяем, не запущен ли уже сервер
        existing_process = self._find_llama_cpp_server()
        if existing_process:
            self.stdout.write(self.style.WARNING(
                f'llama.cpp сервер уже запущен (PID: {existing_process.pid})\n'
                'Используйте ergoms stop-llama-cpp для остановки'
            ))
            return
        
        # Находим llama-server
        server_path = self._find_server_executable()
        if not server_path:
            raise CommandError(
                'llama-server не найден. Установите llama.cpp командой:\n'
                '  ergoms install-llama-cpp'
            )
        
        # Находим модель
        model_path = self._resolve_model_path(options.get('model'))
        if not model_path:
            raise CommandError(
                'Укажите путь к модели через --model или переменную LLAMA_CPP_MODEL'
            )
        
        if not model_path.exists():
            raise CommandError(f'Модель не найдена: {model_path}')
        
        # Формируем команду
        cmd = self._build_command(server_path, model_path, options)
        
        self.stdout.write(f'Запуск llama.cpp сервера...')
        self.stdout.write(f'  Модель: {model_path}')
        self.stdout.write(f'  Хост: {options["host"]}:{options["port"]}')
        self.stdout.write(f'  GPU layers: {options["gpu_layers"]}')
        self.stdout.write(f'  Потоки CPU: {options["threads"]}')
        self.stdout.write(f'  Контекст: {options["context_size"]}')
        
        if options['foreground']:
            self._run_foreground(cmd)
        else:
            self._run_background(cmd, options['host'], options['port'])
    
    def _find_server_executable(self) -> Optional[Path]:
        """Ищет llama-server в packages/llama_cpp"""
        packages_path = Path(settings.PACKAGES_PATH)
        llama_cpp_path = packages_path / 'llama_cpp'
        
        if not llama_cpp_path.exists():
            return None
        
        # Ищем llama-server
        patterns = ['llama-server', 'llama-server.exe', 'server', 'server.exe']
        
        for pattern in patterns:
            for path in llama_cpp_path.rglob(pattern):
                if path.is_file():
                    return path
        
        return None
    
    def _resolve_model_path(self, model_arg: Optional[str]) -> Optional[Path]:
        """Определяет путь к модели"""
        # Приоритет: аргумент командной строки -> env переменная
        model_str = model_arg or os.getenv('LLAMA_CPP_MODEL')
        
        if not model_str:
            return None
        
        model_path = Path(model_str)
        
        # Если абсолютный путь - используем как есть
        if model_path.is_absolute():
            return model_path
        
        # Если относительный - ищем в models
        packages_path = Path(settings.PACKAGES_PATH)
        models_path = packages_path / 'models'
        
        return models_path / model_str
    
    def _build_command(self, server_path: Path, model_path: Path, options: dict) -> List[str]:
        """Формирует команду запуска"""
        cmd = [
            str(server_path),
            '--model', str(model_path),
            '--host', options['host'],
            '--port', str(options['port']),
            '--n-gpu-layers', str(options['gpu_layers']),
            '--threads', str(options['threads']),
            '--ctx-size', str(options['context_size']),
            '--batch-size', str(options['batch_size']),
            '--parallel', str(options['parallel']),
        ]
        
        if options['flash_attn']:
            cmd.append('--flash-attn')
        
        if options['mlock']:
            cmd.append('--mlock')
        
        return cmd
    
    def _find_llama_cpp_server(self) -> Optional[psutil.Process]:
        """Ищет запущенный процесс llama-server"""
        for proc in psutil.process_iter(['pid', 'name', 'cmdline']):
            try:
                name = proc.info.get('name', '').lower()
                cmdline = proc.info.get('cmdline') or []
                cmdline_str = ' '.join(cmdline).lower()
                
                # Проверяем имя процесса или командную строку
                if 'llama-server' in name or 'llama-server' in cmdline_str:
                    return proc
                if 'server' in name and ('gguf' in cmdline_str or '--model' in cmdline_str):
                    return proc
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                continue
        return None
    
    def _run_foreground(self, cmd: List[str]):
        """Запускает сервер в foreground режиме"""
        try:
            process = subprocess.Popen(
                cmd,
                stdout=sys.stdout,
                stderr=sys.stderr,
            )
            process.wait()
        except KeyboardInterrupt:
            self.stdout.write('\nОстановка сервера...')
            process.terminate()
            process.wait()
    
    def _run_background(self, cmd: List[str], host: str, port: int):
        """Запускает сервер в фоновом режиме"""
        try:
            if sys.platform == 'win32':
                # Windows
                process = subprocess.Popen(
                    cmd,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                    creationflags=subprocess.CREATE_NO_WINDOW
                )
            else:
                # Linux/Mac
                process = subprocess.Popen(
                    cmd,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                    start_new_session=True
                )
            
            # Ждем запуска сервера
            self.stdout.write('Ожидание запуска сервера...')
            
            import httpx
            base_url = f"http://{host}:{port}"
            
            for i in range(60):  # Даем больше времени на загрузку модели
                try:
                    # llama.cpp использует /health endpoint
                    response = httpx.get(f"{base_url}/health", timeout=2.0)
                    if response.status_code == 200:
                        self.stdout.write(self.style.SUCCESS(
                            f'\nllama.cpp сервер запущен! (PID: {process.pid})'
                        ))
                        
                        # Получаем и выводим статистику сервера
                        self._print_server_stats(base_url)
                        
                        self.stdout.write(f'\n{self.CYAN}API Endpoints:{self.RESET}')
                        self.stdout.write(f'  Health:     {base_url}/health')
                        self.stdout.write(f'  Completion: {base_url}/completion')
                        self.stdout.write(f'  Props:      {base_url}/props')
                        return
                except Exception:
                    pass
                
                # Проверяем, что процесс еще жив
                if process.poll() is not None:
                    raise CommandError('llama.cpp сервер завершился неожиданно')
                
                time.sleep(1)
                if (i + 1) % 10 == 0:
                    self.stdout.write(f'  ...загрузка модели ({i + 1}s)')
            
            raise CommandError('llama.cpp сервер не стал доступен за отведенное время')
            
        except FileNotFoundError:
            raise CommandError('llama-server не найден')
        except Exception as e:
            raise CommandError(f'Ошибка при запуске llama.cpp: {e}')
    
    def _print_server_stats(self, base_url: str):
        """Выводит статистику сервера llama.cpp"""
        import httpx
        
        self.stdout.write(f'\n{self.BOLD}=== llama.cpp Server Stats ==={self.RESET}')
        
        try:
            # Получаем props (свойства модели и сервера)
            props_response = httpx.get(f"{base_url}/props", timeout=5.0)
            if props_response.status_code == 200:
                props = props_response.json()
                self._print_props(props)
        except Exception as e:
            self.stdout.write(f'  {self.YELLOW}Не удалось получить props: {e}{self.RESET}')
        
        try:
            # Получаем health (статус и слоты)
            health_response = httpx.get(f"{base_url}/health", timeout=5.0)
            if health_response.status_code == 200:
                health = health_response.json()
                self._print_health(health)
        except Exception:
            pass
    
    def _print_props(self, props: Dict[str, Any]):
        """Выводит свойства модели"""
        # Основные параметры
        ctx_size = props.get('default_generation_settings', {}).get('n_ctx', 'N/A')
        n_predict = props.get('default_generation_settings', {}).get('n_predict', 'N/A')
        
        self.stdout.write(f'\n{self.CYAN}Model Configuration:{self.RESET}')
        self.stdout.write(f'  {self.GREEN}Context Size:{self.RESET}    {ctx_size} tokens')
        self.stdout.write(f'  {self.GREEN}Max Predict:{self.RESET}     {n_predict} tokens')
        
        # Параметры генерации
        gen_settings = props.get('default_generation_settings', {})
        temp = gen_settings.get('temperature', 'N/A')
        top_k = gen_settings.get('top_k', 'N/A')
        top_p = gen_settings.get('top_p', 'N/A')
        
        self.stdout.write(f'\n{self.CYAN}Generation Settings:{self.RESET}')
        self.stdout.write(f'  {self.GREEN}Temperature:{self.RESET}     {temp}')
        self.stdout.write(f'  {self.GREEN}Top-K:{self.RESET}           {top_k}')
        self.stdout.write(f'  {self.GREEN}Top-P:{self.RESET}           {top_p}')
        
        # Информация о слотах
        total_slots = props.get('total_slots', 1)
        self.stdout.write(f'\n{self.CYAN}Server:{self.RESET}')
        self.stdout.write(f'  {self.GREEN}Parallel Slots:{self.RESET}  {total_slots}')
    
    def _print_health(self, health: Dict[str, Any]):
        """Выводит статус здоровья сервера"""
        status = health.get('status', 'unknown')
        slots_idle = health.get('slots_idle', 0)
        slots_processing = health.get('slots_processing', 0)
        
        status_color = self.GREEN if status == 'ok' else self.YELLOW
        
        self.stdout.write(f'  {self.GREEN}Status:{self.RESET}          {status_color}{status}{self.RESET}')
        self.stdout.write(f'  {self.GREEN}Slots Idle:{self.RESET}      {slots_idle}')
        self.stdout.write(f'  {self.GREEN}Slots Active:{self.RESET}    {slots_processing}')

