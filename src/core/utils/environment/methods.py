import logging

import os
from pathlib import Path
from typing import Dict, List, Tuple, Optional
from collections import OrderedDict

from src.config.settings.static import MODULES_DIR

logger = logging.getLogger(__name__)

def _find_env_files(configs_dir: str) -> List[Tuple[str, str]]:
    """
    Находит все .env файлы в указанной директории и её подпапках.
    
    Аргументы:
        configs_dir (str): Путь к папке configs
        
    Возвращает:
        List[Tuple[str, str]]: Список кортежей (путь_к_файлу, относительный_путь)
    """
    env_files = []
    configs_path = Path(configs_dir)
    
    if not configs_path.exists():
        logger.warning(f"Папка configs не найдена: {configs_dir}")
        return env_files
    
    # Рекурсивный поиск .env файлов
    for env_file in configs_path.rglob('.env*'):
        if env_file.is_file():
            relative_path = env_file.relative_to(configs_path)
            env_files.append((str(env_file), str(relative_path)))
    
    return env_files


def _parse_env_file(file_path: str) -> Dict[str, str]:
    """
    Парсит .env файл и возвращает словарь переменных окружения.
    
    Аргументы:
        file_path (str): Путь к .env файлу
        
    Возвращает:
        Dict[str, str]: Словарь переменных окружения
    """
    env_vars = {}
    
    try:
        with open(file_path, 'r', encoding='utf-8') as file:
            for line_num, line in enumerate(file, 1):
                line = line.strip()
                
                # Пропускаем пустые строки и комментарии
                if not line or line.startswith('#'):
                    continue
                
                # Проверяем формат KEY=VALUE
                if '=' in line:
                    key, value = line.split('=', 1)
                    key = key.strip()
                    value = value.strip()
                    
                    # Убираем кавычки если есть
                    if value.startswith('"') and value.endswith('"'):
                        value = value[1:-1]
                    elif value.startswith("'") and value.endswith("'"):
                        value = value[1:-1]
                    
                    env_vars[key] = value
                else:
                    logger.warning(f"Некорректный формат в {file_path}:{line_num}: {line}")
    
    except Exception as e:
        logger.error(f"Ошибка при чтении файла {file_path}: {e}")
    
    return env_vars


def _merge_env_variables(env_files: List[Tuple[str, str]]) -> Dict[str, Tuple[str, str]]:
    """
    Объединяет переменные окружения из всех .env файлов.
    
    Аргументы:
        env_files (List[Tuple[str, str]]): Список .env файлов
        
    Возвращает:
        Dict[str, Tuple[str, str]]: Словарь {переменная: (значение, источник)}
    """
    merged_vars = OrderedDict()
    conflicts = []
    
    for file_path, relative_path in env_files:
        env_vars = _parse_env_file(file_path)
        
        for key, value in env_vars.items():
            if key in merged_vars:
                old_value, old_source = merged_vars[key]
                if old_value != value:
                    conflicts.append({
                        'variable': key,
                        'old_value': old_value,
                        'old_source': old_source,
                        'new_value': value,
                        'new_source': relative_path
                    })
                    logger.warning(f"Конфликт переменной {key}: {old_source} vs {relative_path}")
            
            merged_vars[key] = (value, relative_path)
    
    if conflicts:
        logger.warning(f"⚠️  Найдено {len(conflicts)} конфликтов переменных окружения!")
        logger.warning("=" * 60)
        for i, conflict in enumerate(conflicts, 1):
            logger.warning(f"Конфликт #{i}: {conflict['variable']}")
            logger.warning(f"  📁 {conflict['old_source']}: '{conflict['old_value']}'")
            logger.warning(f"  📁 {conflict['new_source']}: '{conflict['new_value']}'")
            logger.warning(f"  ✅ Используется значение из: {conflict['new_source']}")
            logger.warning("-" * 40)
        logger.warning("=" * 60)
    
    return merged_vars


def collect_env_files_from_all_sources() -> Dict[str, str]:
    """
    Собирает все .env файлы из всех источников и возвращает объединённый словарь переменных.
    
    Источники:
    - Папка modules и все её подпапки (ergo_ms/modules/)
    
    Возвращает:
        Dict[str, str]: Словарь переменных окружения {ключ: значение}
    """
    try:
        modules_dir = os.path.abspath(MODULES_DIR)
        
        all_env_files = []
        
        # Собираем .env файлы из папки modules и всех её подпапок
        modules_env_files = _find_env_files_in_directory(modules_dir, "modules")
        all_env_files.extend(modules_env_files)
        
        if not all_env_files:
            logger.info("Не найдено ни одного .env файла в папке modules")
            return {}
        
        # Объединяем переменные
        merged_vars = _merge_env_variables(all_env_files)
        
        if not merged_vars:
            logger.info("Не найдено ни одной переменной окружения в папке modules")
            return {}
        
        # Преобразуем в простой словарь {ключ: значение}
        env_dict = {key: value for key, (value, source) in merged_vars.items()}
        
        logger.info(f"✅ Загружено {len(env_dict)} переменных окружения из папки modules")
        
        return env_dict
        
    except Exception as e:
        logger.error(f"Ошибка при сборе .env файлов: {e}")
        return {}


def _find_env_files_in_directory(directory: str, source_name: str) -> List[Tuple[str, str]]:
    """
    Находит все .env файлы в указанной директории и её подпапках.
    
    Аргументы:
        directory (str): Путь к директории для поиска
        source_name (str): Название источника для логирования
        
    Возвращает:
        List[Tuple[str, str]]: Список кортежей (путь_к_файлу, относительный_путь)
    """
    env_files = []
    search_path = Path(directory)
    
    if not search_path.exists():
        logger.warning(f"Директория {source_name} не найдена: {directory}")
        return env_files
    
    # Рекурсивный поиск .env файлов
    for env_file in search_path.rglob('*.env*'):
        if env_file.is_file():
            # Создаем относительный путь от корня проекта
            try:
                relative_path = env_file.relative_to(search_path)
                env_files.append((str(env_file), f"{source_name}/{relative_path}"))
            except ValueError:
                # Если не удается создать относительный путь, используем имя файла
                env_files.append((str(env_file), f"{source_name}/{env_file.name}"))
    
    return env_files


def collect_env_files_from_configs() -> Dict[str, str]:
    """
    Собирает все .env файлы из всех источников (обратная совместимость).
    
    Возвращает:
        Dict[str, str]: Словарь переменных окружения {ключ: значение}
    """
    return collect_env_files_from_all_sources()


def get_env_sources() -> Dict[str, List[str]]:
    """
    Возвращает информацию о том, из каких файлов взяты переменные окружения.
    
    Возвращает:
        Dict[str, List[str]]: Словарь {источник: [переменные]}
    """
    modules_dir = os.path.abspath(MODULES_DIR)
    
    all_env_files = []
    
    # Собираем .env файлы из папки modules
    modules_env_files = _find_env_files_in_directory(modules_dir, "modules")
    all_env_files.extend(modules_env_files)
    
    sources = {}
    for file_path, relative_path in all_env_files:
        env_vars = _parse_env_file(file_path)
        sources[relative_path] = list(env_vars.keys())
    
    return sources