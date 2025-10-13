"""
Django management команда для обнаружения модулей и подмодулей.

Использование:
    python manage.py discover_modules
"""

import os
from pathlib import Path
from django.core.management.base import BaseCommand, CommandError
from django.conf import settings


class Command(BaseCommand):
    """Команда для обнаружения модулей и подмодулей Django приложения."""
    
    help = 'Обнаружение модулей и подмодулей в проекте'
    
    def add_arguments(self, parser):
        """Добавление аргументов команды."""
        parser.add_argument(
            '--detailed',
            action='store_true',
            help='Показать детальную информацию о каждом модуле',
        )
        parser.add_argument(
            '--path',
            type=str,
            help='Путь к директории для анализа (по умолчанию src)',
        )
    
    def handle(self, *args, **options):
        """Выполнение команды."""
        try:
            # Определяем путь к проекту
            if options['path']:
                project_root = Path(options['path'])
            else:
                # Получаем путь к src из настроек Django
                # BASE_DIR уже указывает на папку src, поэтому не добавляем 'src'
                project_root = Path(settings.BASE_DIR)
            
            if not project_root.exists():
                raise CommandError(f"Директория {project_root} не существует")
            
            self.stdout.write(
                self.style.SUCCESS("🔍 Обнаружение модулей и подмодулей Django приложения")
            )
            self.stdout.write("=" * 60)
            
            # Обнаруживаем core модули
            core_dir = project_root / 'core'
            if core_dir.exists():
                self.stdout.write("\n📁 CORE МОДУЛИ:")
                self.stdout.write("-" * 30)
                core_modules = self._discover_modules(core_dir, "src.core")
                self._print_modules(core_modules, "core", options['detailed'])
            else:
                self.stdout.write(self.style.WARNING("   Директория core не найдена"))
            
            # Обнаруживаем modules
            modules_dir = project_root / 'modules'
            if modules_dir.exists():
                self.stdout.write("\n📁 МОДУЛИ:")
                self.stdout.write("-" * 30)
                modules = self._discover_modules(modules_dir, "src.modules")
                self._print_modules(modules, "modules", options['detailed'])
            else:
                self.stdout.write(self.style.WARNING("   Директория modules не найдена"))
            
        except Exception as e:
            raise CommandError(f"Ошибка при обнаружении модулей: {e}")
    
    def _discover_modules(self, base_dir: Path, base_module: str) -> list:
        """Обнаружение модулей в указанной директории."""
        modules = []
        
        for item in base_dir.iterdir():
            if item.is_dir() and not item.name.startswith('_'):
                apps_py = item / 'apps.py'
                if apps_py.exists():
                    module_info = {
                        'name': item.name,
                        'path': str(item.relative_to(base_dir.parent)),
                        'full_path': str(item),
                        'module_path': f"{base_module}.{item.name}",
                        'has_apps': True,
                        'has_urls': (item / 'urls.py').exists(),
                        'has_models': (item / 'models.py').exists(),
                        'has_views': (item / 'views.py').exists(),
                        'has_migrations': (item / 'migrations').exists(),
                        'has_admin': (item / 'admin.py').exists(),
                        'has_serializers': (item / 'serializers.py').exists(),
                        'has_signals': (item / 'signals.py').exists(),
                        'has_tasks': (item / 'tasks.py').exists(),
                        'submodules': []
                    }
                    
                    # Проверяем подмодули
                    submodules = self._discover_submodules_in_module(item, f"{base_module}.{item.name}")
                    module_info['submodules'] = submodules
                    
                    modules.append(module_info)
        
        return modules
    
    def _discover_submodules_in_module(self, module_dir: Path, module_path: str) -> list:
        """Обнаружение подмодулей внутри модуля."""
        submodules = []
        
        for item in module_dir.iterdir():
            if (item.is_dir() and 
                not item.name.startswith('_') and 
                not item.name in ['migrations', 'management', '__pycache__'] and
                (item / '__init__.py').exists() and
                (item / 'apps.py').exists()):  # Только папки с apps.py
                
                submodule_info = {
                    'name': item.name,
                    'path': str(item.relative_to(module_dir)),
                    'full_path': str(item),
                    'module_path': f"{module_path}.{item.name}",
                    'has_apps': True,
                    'has_urls': (item / 'urls.py').exists(),
                    'has_models': (item / 'models.py').exists(),
                    'has_views': (item / 'views.py').exists(),
                    'has_admin': (item / 'admin.py').exists(),
                    'has_serializers': (item / 'serializers.py').exists(),
                    'type': 'submodule'
                }
                
                submodules.append(submodule_info)
        
        return submodules
    
    def _print_modules(self, modules: list, module_type: str, detailed: bool = False):
        """Вывод информации о модулях."""
        if not modules:
            self.stdout.write(f"   Нет {module_type} модулей")
            return
        
        for module in modules:
            # Простой статус: 📱 если есть apps.py, иначе 📄
            status = "📱" if module['has_apps'] else "📄"
            
            self.stdout.write(f"   {status} {module['name']}")
            self.stdout.write(f"      Путь: {module['path']}")
            self.stdout.write(f"      Модуль: {module['module_path']}")
            
            if detailed:
                self.stdout.write(f"      Полный путь: {module['full_path']}")
                self._print_module_details(module)
            
            if module['submodules']:
                self.stdout.write(f"      Подмодули: {len(module['submodules'])}")
                for submodule in module['submodules']:
                    sub_status = "📱" if submodule['has_apps'] else "📄"
                    self.stdout.write(f"        {sub_status} {submodule['name']} ({submodule['module_path']})")
            self.stdout.write("")
    
    def _print_module_details(self, module: dict):
        """Вывод детальной информации о модуле."""
        details = []
        if module['has_urls']:
            details.append("URLs")
        if module['has_models']:
            details.append("Models")
        if module['has_views']:
            details.append("Views")
        if module['has_admin']:
            details.append("Admin")
        if module['has_serializers']:
            details.append("Serializers")
        if module['has_signals']:
            details.append("Signals")
        if module['has_tasks']:
            details.append("Tasks")
        if module['has_migrations']:
            details.append("Migrations")
        
        if details:
            self.stdout.write(f"      Компоненты: {', '.join(details)}") 