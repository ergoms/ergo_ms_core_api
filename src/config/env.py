"""
Файл для загрузки переменных окружения из .env файлов для Django-приложения.

Функциональность:
    - Загрузка переменных окружения из основного .env файла в корне проекта (SYSTEM_DIR)
    - Загрузка переменных окружения из .env файлов в папке modules (имеют приоритет)
    - Предоставление доступа к переменным окружения через объект env
    - Автоматическое преобразование типов данных переменных окружения

Приоритет загрузки:
    1. Основной .env файл из корня проекта (SYSTEM_DIR/.env)
    2. .env файлы из папки modules и её подпапок (переопределяют основной .env)

Структура:
    ENV_FILE_PATH: Путь к основному .env файлу в корне проекта (SYSTEM_DIR)
    env: Объект environ.Env для доступа к переменным окружения

Использование:
    from src.config.env import env
    
    DEBUG = env.bool('DEBUG', default=False)
    SECRET_KEY = env.str('SECRET_KEY')
    DATABASE_URL = env.db('DATABASE_URL')
"""

import environ
import os
import logging

from src.config.paths import ENV_FILE_PATH
from src.core.utils.environment.methods import collect_env_files_from_all_sources

logger = logging.getLogger(__name__)

# Собираем переменные из всех .env файлов в папке modules
modules_env_vars = collect_env_files_from_all_sources()

# Инициализация объекта для работы с переменными окружения
env = environ.Env()

# Отслеживаем переменные, загруженные из основного .env файла
main_env_vars = set()

# Сначала загружаем основной .env файл из корня проекта (SYSTEM_DIR)
if os.path.exists(ENV_FILE_PATH):
    # Читаем основной .env файл и отслеживаем его переменные
    with open(ENV_FILE_PATH, 'r', encoding='utf-8') as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith('#') and '=' in line:
                key = line.split('=', 1)[0].strip()
                main_env_vars.add(key)
    # Загружаем переменные из .env файла в os.environ
    env.read_env(ENV_FILE_PATH)
    logger.info(f"✅ Загружен основной .env файл из корня проекта: {ENV_FILE_PATH}")
    logger.info(f"   Найдено переменных: {len(main_env_vars)}")
else:
    logger.warning(f"⚠️  Файл .env не найден по пути: {ENV_FILE_PATH}")

# Затем добавляем переменные из modules (они имеют приоритет над основным .env)
if modules_env_vars:
    overridden_vars = []
    for key, value in modules_env_vars.items():
        # Проверяем, была ли переменная определена в основном .env файле
        if key in main_env_vars:
            overridden_vars.append(key)
        os.environ[key] = value
    
    # Логируем только если есть переопределения
    if overridden_vars:
        logger.warning(f"⚠️  Переменные из modules переопределили {len(overridden_vars)} переменных из основного .env:")
        for var in overridden_vars:
            logger.warning(f"  - {var}")