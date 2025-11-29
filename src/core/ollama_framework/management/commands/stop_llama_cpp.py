"""
Django команда для остановки llama.cpp сервера
"""

import psutil

from django.core.management.base import BaseCommand


class Command(BaseCommand):
    help = 'Останавливает llama.cpp сервер'
    
    def add_arguments(self, parser):
        parser.add_argument(
            '--force',
            action='store_true',
            help='Принудительно завершить процесс (SIGKILL вместо SIGTERM)',
        )
    
    def handle(self, *args, **options):
        force = options.get('force', False)
        
        processes = self._find_llama_cpp_processes()
        
        if not processes:
            self.stdout.write(self.style.WARNING('llama.cpp сервер не запущен'))
            return
        
        for proc in processes:
            try:
                pid = proc.pid
                name = proc.name()
                
                if force:
                    proc.kill()
                    self.stdout.write(f'Процесс {name} (PID: {pid}) принудительно завершен')
                else:
                    proc.terminate()
                    # Ждем завершения
                    proc.wait(timeout=10)
                    self.stdout.write(f'Процесс {name} (PID: {pid}) остановлен')
                    
            except psutil.NoSuchProcess:
                self.stdout.write(f'Процесс уже завершен')
            except psutil.TimeoutExpired:
                # Если не завершился за 10 секунд - принудительно
                proc.kill()
                self.stdout.write(self.style.WARNING(
                    f'Процесс {name} (PID: {pid}) принудительно завершен (таймаут)'
                ))
            except Exception as e:
                self.stdout.write(self.style.ERROR(f'Ошибка при остановке: {e}'))
        
        self.stdout.write(self.style.SUCCESS('llama.cpp сервер остановлен'))
    
    def _find_llama_cpp_processes(self):
        """Ищет все запущенные процессы llama.cpp"""
        processes = []
        
        for proc in psutil.process_iter(['pid', 'name', 'cmdline']):
            try:
                name = proc.info.get('name', '').lower()
                cmdline = proc.info.get('cmdline') or []
                cmdline_str = ' '.join(cmdline).lower()
                
                # Проверяем имя процесса или командную строку
                if 'llama-server' in name or 'llama-server' in cmdline_str:
                    processes.append(proc)
                elif 'server' in name and ('gguf' in cmdline_str or '--model' in cmdline_str):
                    processes.append(proc)
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                continue
        
        return processes

