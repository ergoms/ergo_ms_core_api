"""
Базовый класс для выполнения Django команд через Poetry.
"""

import os
import subprocess
import sys

from typing import Optional


def _extract_test_module(args: list[str]) -> Optional[str]:
    """
    Извлекает имя модуля из аргументов команды test.
    
    Примеры:
        ['modules.crm_remastered.api.tests.TestClass'] -> 'crm_remastered'
        ['modules.lms.api.tests'] -> 'lms'
        ['--keepdb', 'modules.tasks.api.tests'] -> 'tasks'
        ['src.core.utils.tests'] -> None
    """
    for arg in args:
        if arg.startswith('-'):
            continue
        if arg.startswith('modules.'):
            parts = arg.split('.')
            if len(parts) >= 2:
                return parts[1]
    return None


def _get_deploy_type() -> str:
    """Возвращает DJANGO_SETTINGS_MODULE (как manage.py и deploy.py)."""
    from src.config.deploy import get_settings_module

    return get_settings_module()


class PoetryCommand:
    """Базовый класс для выполнения команд через Poetry."""
    
    poetry_command_name: Optional[str] = None
    django_command_name: Optional[str] = None
    script_command: Optional[str] = None
    _test_args: list[str] = []
    
    def __init__(self, command_name: Optional[str] = None):
        """Инициализация команды."""
        self.command_name = command_name or self.django_command_name or self.script_command
        self._test_args = []

        if not self.command_name:
            raise ValueError("Не указано имя команды для выполнения.")
        
        if not self.poetry_command_name:
            self.poetry_command_name = self.command_name

    def run(self, *args) -> int:
        """Выполнение команды."""
        self._test_args = list(args)
        
        filtered_args = [arg for arg in args if arg and arg != '--full']
        args_str = " ".join(str(arg) for arg in filtered_args)

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
            code = e.code
            if isinstance(code, str):
                print(code, file=sys.stderr)
                return 1
            return code if code is not None else 0
        except UnicodeDecodeError as e:
            print(
                'Ошибка кодировки ввода (часто Windows-терминал → Docker).\n'
                'Используйте латиницу в пароле/email или:\n'
                '  export DJANGO_SUPERUSER_USERNAME=...\n'
                '  export DJANGO_SUPERUSER_PASSWORD=...\n'
                '  export DJANGO_SUPERUSER_EMAIL=...\n'
                '  ergoms api createsuperuser --noinput\n'
                f'Детали: {e}',
                file=sys.stderr,
            )
            return 1
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

            project_root = os.path.abspath(os.path.join(api_dir, '..', '..'))
            if project_root not in sys.path:
                sys.path.insert(0, project_root)

            warmup_commands = ('warmup_caches', 'warmup_celery')
            if self.command_name in warmup_commands:
                os.environ['DJANGO_SETTINGS_MODULE'] = 'src.config.patterns.warmup'
            elif self.command_name == 'test':
                self._init_test_settings()
            else:
                deploy_type = _get_deploy_type()
                os.environ['DJANGO_SETTINGS_MODULE'] = deploy_type

            import django
            if not django.conf.settings.configured:
                django.setup()
        except Exception as e:
            print(f"Предупреждение: Не удалось инициализировать Django: {e}")

    def _init_test_settings(self):
        """Инициализация настроек для команды test."""
        use_full = '--full' in self._test_args
        
        if use_full:
            os.environ['TEST_FULL_APPS'] = '1'
            deploy_type = _get_deploy_type()
            os.environ['DJANGO_SETTINGS_MODULE'] = deploy_type
            return
        
        target_module = _extract_test_module(self._test_args)
        
        if target_module:
            os.environ['TEST_TARGET_MODULE'] = target_module
            os.environ['DJANGO_SETTINGS_MODULE'] = 'src.config.patterns.test'
        else:
            deploy_type = _get_deploy_type()
            os.environ['DJANGO_SETTINGS_MODULE'] = deploy_type