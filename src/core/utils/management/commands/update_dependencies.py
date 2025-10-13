"""
Команда для обновления версий библиотек в pyproject.toml до самых новейших.

Этот файл включает в себя реализацию Django команды для автоматического
обновления версий зависимостей в pyproject.toml до последних доступных версий.

Пример использования:
    python src/manage.py update_dependencies
    python src/manage.py update_dependencies --dry-run
    python src/manage.py update_dependencies --package django
"""

import os
import re
import subprocess
import logging
from typing import Any, Dict, List, Tuple, Optional
from pathlib import Path

from django.core.management.base import BaseCommand, CommandError
from django.conf import settings

# Настройка логгера
logger = logging.getLogger('utils')

class Command(BaseCommand):
    """
    Команда Django для обновления версий библиотек в pyproject.toml.

    Attributes:
        help (str): Описание команды для справки Django.
    """
    help = 'Обновление версий библиотек в pyproject.toml до самых новейших'

    def add_arguments(self, parser) -> None:
        """
        Добавляет аргументы командной строки для команды.

        Args:
            parser: Парсер аргументов Django.
        """
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Показать какие обновления будут сделаны без их применения'
        )
        parser.add_argument(
            '--package',
            type=str,
            help='Обновить только указанную библиотеку'
        )
        parser.add_argument(
            '--exclude',
            nargs='+',
            help='Исключить указанные библиотеки из обновления'
        )

    def get_pyproject_path(self) -> Path:
        """
        Получает путь к файлу pyproject.toml.

        Returns:
            Path: Путь к файлу pyproject.toml

        Raises:
            CommandError: Если файл pyproject.toml не найден
        """
        # Ищем pyproject.toml в корне проекта
        current_dir = Path(settings.BASE_DIR).parent
        pyproject_path = current_dir / 'pyproject.toml'
        
        if not pyproject_path.exists():
            raise CommandError(f'Файл pyproject.toml не найден по пути: {pyproject_path}')
        
        return pyproject_path

    def parse_pyproject_toml(self, pyproject_path: Path) -> Tuple[str, Dict[str, str]]:
        """
        Парсит файл pyproject.toml и извлекает зависимости.

        Args:
            pyproject_path (Path): Путь к файлу pyproject.toml

        Returns:
            Tuple[str, Dict[str, str]]: Содержимое файла и словарь зависимостей
        """
        with open(pyproject_path, 'r', encoding='utf-8') as file:
            content = file.read()
        
        # Извлекаем зависимости из секции [project]
        dependencies = {}
        in_dependencies = False
        
        for line in content.split('\n'):
            line = line.strip()
            
            if line == 'dependencies = [':
                in_dependencies = True
                continue
            elif line == ']' and in_dependencies:
                in_dependencies = False
                break
            
            if in_dependencies and line.startswith('"'):
                # Убираем кавычки и запятую в конце
                dep_line = line.rstrip(',').strip('"')
                if '>=' in dep_line:
                    package_name, version = dep_line.split('>=', 1)
                    dependencies[package_name] = version
        
        return content, dependencies

    def get_latest_version(self, package_name: str) -> Optional[str]:
        """
        Получает последнюю версию пакета через pip.

        Args:
            package_name (str): Имя пакета

        Returns:
            Optional[str]: Последняя версия или None если не удалось получить
        """
        try:
            result = subprocess.run(
                ['pip', 'index', 'versions', package_name],
                capture_output=True,
                text=True,
                timeout=30
            )
            
            if result.returncode == 0:
                # Парсим вывод pip index versions
                output_lines = result.stdout.strip().split('\n')
                for line in output_lines:
                    if 'LATEST:' in line:
                        # Извлекаем версию после LATEST:
                        latest_version = line.split('LATEST:')[1].strip()
                        return latest_version
            
            return None
        except (subprocess.TimeoutExpired, subprocess.CalledProcessError) as e:
            logger.warning(f'Не удалось получить версию для {package_name}: {e}')
            return None

    def update_dependencies(self, content: str, dependencies: Dict[str, str], 
                          package_filter: Optional[str] = None, 
                          exclude_packages: Optional[List[str]] = None) -> Tuple[str, Dict[str, Tuple[str, str]]]:
        """
        Обновляет зависимости в содержимом файла.

        Args:
            content (str): Содержимое файла pyproject.toml
            dependencies (Dict[str, str]): Текущие зависимости
            package_filter (Optional[str]): Фильтр по конкретному пакету
            exclude_packages (Optional[List[str]]): Список исключаемых пакетов

        Returns:
            Tuple[str, Dict[str, Tuple[str, str]]]: Обновленное содержимое и словарь изменений
        """
        updated_content = content
        changes = {}
        
        exclude_packages = exclude_packages or []
        
        for package_name, current_version in dependencies.items():
            # Пропускаем если указан фильтр и пакет не подходит
            if package_filter and package_name != package_filter:
                continue
            
            # Пропускаем исключенные пакеты
            if package_name in exclude_packages:
                continue
            
            # Получаем последнюю версию
            latest_version = self.get_latest_version(package_name)
            
            if latest_version and latest_version != current_version:
                changes[package_name] = (current_version, latest_version)
                
                # Обновляем в содержимом файла
                old_pattern = f'"{package_name}>={current_version}"'
                new_pattern = f'"{package_name}>={latest_version}"'
                updated_content = updated_content.replace(old_pattern, new_pattern)
        
        return updated_content, changes

    def handle(self, *args: Any, **options: Any) -> None:
        """
        Выполняет команду обновления зависимостей.

        Args:
            *args: Позиционные аргументы
            **options: Именованные аргументы

        Raises:
            CommandError: Если возникла ошибка при обновлении
        """
        dry_run = options.get('dry_run', False)
        package_filter = options.get('package')
        exclude_packages = options.get('exclude', [])
        
        try:
            # Получаем путь к pyproject.toml
            pyproject_path = self.get_pyproject_path()
            self.stdout.write(f'Найден файл: {pyproject_path}')
            
            # Парсим файл
            content, dependencies = self.parse_pyproject_toml(pyproject_path)
            self.stdout.write(f'Найдено зависимостей: {len(dependencies)}')
            
            if package_filter:
                self.stdout.write(f'Обновляем только пакет: {package_filter}')
            
            if exclude_packages:
                self.stdout.write(f'Исключаем пакеты: {", ".join(exclude_packages)}')
            
            # Обновляем зависимости
            updated_content, changes = self.update_dependencies(
                content, dependencies, package_filter, exclude_packages
            )
            
            if not changes:
                self.stdout.write(self.style.SUCCESS('Все зависимости уже обновлены до последних версий!'))
                return
            
            # Показываем изменения
            self.stdout.write('\nНайденные обновления:')
            for package_name, (old_version, new_version) in changes.items():
                self.stdout.write(f'  {package_name}: {old_version} → {new_version}')
            
            if dry_run:
                self.stdout.write(self.style.WARNING('\nРежим dry-run: изменения не применены'))
                return
            
            # Применяем изменения
            with open(pyproject_path, 'w', encoding='utf-8') as file:
                file.write(updated_content)
            
            self.stdout.write(self.style.SUCCESS(f'\nУспешно обновлено {len(changes)} зависимостей!'))
            
        except Exception as e:
            logger.error(f'Ошибка при обновлении зависимостей: {e}')
            raise CommandError(f'Не удалось обновить зависимости: {e}') 