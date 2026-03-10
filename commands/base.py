"""
Базовый класс для выполнения Django команд через Poetry.
"""

import os
import subprocess
import sys

from typing import Optional

from src.core.utils.auto_api.auto_config import get_env_deploy_type


class PoetryCommand:
    """Базовый класс для выполнения команд через Poetry."""
    
    poetry_command_name: Optional[str] = None
    django_command_name: Optional[str] = None
    script_command: Optional[str] = None
    
    def __init__(self, command_name: Optional[str] = None):
        """Инициализация команды."""
        self.command_name = command_name or self.django_command_name or self.script_command

        if not self.command_name:
            raise ValueError("Не указано имя команды для выполнения.")
        
        if not self.poetry_command_name:
            self.poetry_command_name = self.command_name

    def run(self, *args) -> int:
        """Выполнение команды."""
        args_str = " ".join(str(arg) for arg in args if arg)

        if self.django_command_name:
            return self._run_django(args_str)
        elif self.script_command:
            return self._run_script(f"{self.script_command} {args_str}".strip())
        else:
            raise RuntimeError("Не удалось определить тип команды.")

    def _run_django(self, args_str: str) -> int:
        """Выполнение Django команды."""
        try:
            self._init_django()
            
            from django.core.management import execute_from_command_line
            
            django_args = ['manage.py', self.command_name]
            if self.command_name in ('warmup_caches', 'warmup_celery'):
                django_args.append('--skip-checks')
            if args_str:
                django_args.extend(args_str.split())


            
            print(f"Выполняется Django команда: {' '.join(django_args)}")
            execute_from_command_line(django_args)
            return 0
            
        except SystemExit as e:
            return e.code if e.code is not None else 0
        except Exception as e:
            print(f"Ошибка при выполнении Django команды: {e}")
            return 1

    def _run_script(self, command: str) -> int:
        """Выполнение пользовательской команды."""
        print(f"Выполняется команда: {command}")
        
        try:
            result = subprocess.run(
                command, 
                shell=True, 
                cwd=os.path.dirname(os.path.dirname(__file__)),
                capture_output=False,
                text=True
            )
            
            if result.returncode != 0:
                print(f"Команда завершилась с ошибкой (код: {result.returncode})")
                return result.returncode
            
            return 0
            
        except Exception as e:
            print(f"Ошибка при выполнении команды: {e}")
            return 1

    def _init_django(self):
        """Инициализация Django."""
        try:
            commands_dir = os.path.dirname(os.path.abspath(__file__))
            api_dir = os.path.dirname(commands_dir)
            project_path = os.path.join(api_dir, 'src')
            if project_path not in sys.path:
                sys.path.insert(0, project_path)

            warmup_commands = ('warmup_caches', 'warmup_celery')
            if self.command_name in warmup_commands:
                project_root = os.path.abspath(os.path.join(api_dir, '..', '..'))
                if project_root not in sys.path:
                    sys.path.insert(0, project_root)
                os.environ['DJANGO_SETTINGS_MODULE'] = 'src.config.patterns.warmup'
            else:
                deploy_type = get_env_deploy_type()
                os.environ.setdefault('DJANGO_SETTINGS_MODULE', deploy_type)

            import django
            if not django.conf.settings.configured:
                django.setup()
        except Exception as e:
            print(f"Предупреждение: Не удалось инициализировать Django: {e}")