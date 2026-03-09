"""
Централизованная объектно-ориентированная система управления конфигурацией баз данных.
Использует паттерн Strategy и наследование для гибкой работы с разными типами БД.
"""

import os
import yaml
import logging
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Dict, Optional, List, Tuple
from urllib.parse import quote_plus

logger = logging.getLogger('utils.database.config')

_YAML_CACHE: Dict[Path, tuple] = {}


def _get_cached_yaml(config_path: Path) -> Optional[Dict]:
    """Читает databases.yaml с общим кэшем. Инвалидация по mtime."""
    try:
        resolved = config_path.resolve()
        mtime = resolved.stat().st_mtime
    except OSError:
        return None
    if resolved in _YAML_CACHE:
        cached_mtime, cached_config = _YAML_CACHE[resolved]
        if cached_mtime == mtime:
            return cached_config
    if not resolved.exists():
        logger.warning(f"Файл конфигурации не найден: {config_path}")
        return None
    try:
        with open(resolved, 'r', encoding='utf-8') as file:
            config = yaml.safe_load(file)
        if not config or 'databases' not in config:
            logger.error("Неверный формат файла конфигурации")
            return None
        _YAML_CACHE[resolved] = (mtime, config['databases'])
        logger.info(f"Загружена конфигурация из {config_path}")
        return config['databases']
    except Exception as e:
        logger.error(f"Ошибка при чтении конфигурации: {e}")
        return None


# ==================== Константы ====================

DB_ENGINES = {
    'postgresql': 'django.db.backends.postgresql',
    'mysql': 'mysql.connector.django',
    'sqlite': 'django.db.backends.sqlite3',
    'mssql': 'django.db.backends.sqlserver',
}


# ==================== Базовый класс ====================

class BaseDatabaseConfigLoader(ABC):
    """
    Базовый абстрактный класс для загрузки конфигурации баз данных.
    Предоставляет общую логику работы с databases.yaml.
    """
    
    def __init__(self, system_dir: Path):
        """
        Инициализация загрузчика конфигурации.
        
        Args:
            system_dir: Путь к корневой директории системы
        """
        self.system_dir = system_dir
        self.config_path = system_dir / 'databases.yaml'
        self._raw_config: Optional[Dict] = None
        self._loaded = False
    
    def _load_yaml_config(self) -> Optional[Dict]:
        """Загружает YAML через общий кэш (один файл — одно чтение)."""
        return _get_cached_yaml(self.config_path)
    
    def load_config(self) -> Dict:
        """
        Загружает конфигурацию БД.
        
        Returns:
            Словарь с конфигурацией БД
        """
        if not self._loaded:
            self._raw_config = self._load_yaml_config()
            self._loaded = True
        
        return self._process_config(self._raw_config)
    
    @abstractmethod
    def _process_config(self, raw_config: Optional[Dict]) -> Dict:
        """
        Обрабатывает сырую конфигурацию и возвращает готовую к использованию.
        
        Args:
            raw_config: Сырая конфигурация из YAML
            
        Returns:
            Обработанная конфигурация
        """
        pass
    
    def get_section_config(self, section_name: str) -> Optional[Dict]:
        """
        Получает конфигурацию конкретной секции.
        
        Args:
            section_name: Имя секции (например, 'default', 'celery')
            
        Returns:
            Конфигурация секции или None
        """
        if self._raw_config is None:
            self._raw_config = self._load_yaml_config()
        
        if self._raw_config is None:
            return None
        
        return self._raw_config.get(section_name)
    
    def get_available_sections(self) -> List[str]:
        """
        Возвращает список доступных секций БД.
        
        Returns:
            Список имен секций
        """
        if self._raw_config is None:
            self._raw_config = self._load_yaml_config()
        
        if self._raw_config is None:
            return []
        
        return list(self._raw_config.keys())


# ==================== Класс для проверки подключения ====================

class DatabaseConnectionTester:
    """
    Класс для тестирования подключений к различным типам БД.
    """
    
    @staticmethod
    def test_postgresql(host: str, port: int, user: str, password: str, dbname: str) -> bool:
        """Тестирует подключение к PostgreSQL"""
        try:
            import psycopg2
            connection = psycopg2.connect(
                dbname=dbname,
                user=user,
                password=password,
                host=host,
                port=port,
                connect_timeout=5
            )
            connection.close()
            return True
        except Exception as e:
            # Извлекаем понятное сообщение об ошибке
            error_message = DatabaseConnectionTester._extract_postgresql_error(e, dbname)
            logger.error(f"PostgreSQL подключение не удалось: {error_message}")
            return False
    
    @staticmethod
    def _extract_postgresql_error(e: Exception, dbname: str = '') -> str:
        """
        Извлекает понятное сообщение об ошибке из исключения PostgreSQL.
        Правильно обрабатывает ошибки декодирования и разделяет их от ошибок подключения.
        
        Args:
            e: Исключение от psycopg2
            dbname: Имя базы данных (для более точных сообщений об ошибках)
        """
        # Сначала пытаемся извлечь понятное сообщение из args исключения
        messages = []
        decode_error_occurred = False
        
        for arg in e.args:
            if isinstance(arg, bytes):
                # Пытаемся декодировать байты
                try:
                    # Сначала пробуем UTF-8
                    decoded = arg.decode('utf-8', errors='strict')
                    messages.append(decoded)
                except UnicodeDecodeError:
                    decode_error_occurred = True
                    try:
                        # Пробуем cp1251 (Windows кодировка)
                        decoded = arg.decode('cp1251', errors='replace')
                        messages.append(decoded)
                    except Exception:
                        # Если не получилось - используем repr
                        messages.append(repr(arg))
            else:
                # Обычные строки
                try:
                    messages.append(str(arg))
                except Exception as decode_err:
                    # Если даже str() вызывает ошибку декодирования
                    decode_error_occurred = True
                    messages.append(f"[Ошибка декодирования: {type(decode_err).__name__}]")
        
        # Формируем итоговое сообщение
        if messages:
            base_message = ' '.join(messages).strip()
        else:
            base_message = str(type(e).__name__)
        
        # Определяем тип ошибки для более понятного сообщения
        error_type = type(e).__name__
        error_lower = base_message.lower()
        
        # Если произошла ошибка декодирования, добавляем пояснение
        if decode_error_occurred:
            # Пытаемся определить реальную причину ошибки подключения
            if 'password authentication failed' in error_lower or 'authentication failed' in error_lower:
                return "Ошибка авторизации: неверное имя пользователя или пароль"
            elif 'could not connect' in error_lower or 'connection refused' in error_lower:
                return "Не удалось подключиться к серверу: проверьте хост и порт"
            elif 'timeout' in error_lower:
                return "Превышено время ожидания подключения: сервер недоступен"
            elif 'database' in error_lower and 'does not exist' in error_lower:
                if dbname:
                    return f"База данных '{dbname}' не найдена"
                else:
                    return "База данных не найдена"
            else:
                return f"Ошибка подключения (также произошла ошибка декодирования сообщения): {base_message[:200]}"
        
        # Если ошибки декодирования не было, анализируем обычные ошибки
        if 'password authentication failed' in error_lower or 'authentication failed' in error_lower:
            return "Ошибка авторизации: неверное имя пользователя или пароль"
        elif 'could not connect' in error_lower or 'connection refused' in error_lower:
            return "Не удалось подключиться к серверу: проверьте хост и порт"
        elif 'timeout' in error_lower or 'timed out' in error_lower:
            return "Превышено время ожидания подключения: сервер недоступен"
        elif 'database' in error_lower and 'does not exist' in error_lower:
            if dbname:
                return f"База данных '{dbname}' не найдена"
            else:
                return "База данных не найдена"
        elif 'could not translate host name' in error_lower or 'getaddrinfo failed' in error_lower:
            return "Не удалось разрешить имя хоста: проверьте правильность адреса"
        else:
            # Возвращаем базовое сообщение, ограничив его длину
            return base_message[:500] if len(base_message) > 500 else base_message
    
    @staticmethod
    def test_mysql(host: str, port: int, user: str, password: str, database: str) -> bool:
        """Тестирует подключение к MySQL"""
        try:
            import mysql.connector
            connection = mysql.connector.connect(
                database=database,
                user=user,
                password=password,
                host=host,
                port=port,
                connection_timeout=5
            )
            connection.close()
            return True
        except Exception as e:
            logger.error(f"MySQL подключение не удалось: {str(e)}")
            return False
    
    @staticmethod
    def test_sqlite(db_path: str) -> bool:
        """Тестирует подключение к SQLite"""
        try:
            import sqlite3
            connection = sqlite3.connect(db_path, timeout=5)
            connection.close()
            return True
        except Exception as e:
            logger.error(f"SQLite подключение не удалось: {str(e)}")
            return False
    
    @staticmethod
    def test_mssql(host: str, port: int, user: str, password: str, database: str) -> bool:
        """Тестирует подключение к MS SQL Server"""
        try:
            import pyodbc
            connection_string = (
                f"DRIVER={{ODBC Driver 17 for SQL Server}};"
                f"SERVER={host},{port};"
                f"DATABASE={database};"
                f"UID={user};"
                f"PWD={password};"
                f"Connection Timeout=5;"
            )
            connection = pyodbc.connect(connection_string)
            connection.close()
            return True
        except Exception as e:
            logger.error(f"MSSQL подключение не удалось: {str(e)}")
            return False
    
    @classmethod
    def test_connection(cls, engine: str, config: Dict) -> bool:
        """
        Тестирует подключение к БД на основе типа движка.
        
        Args:
            engine: Тип БД ('postgresql', 'mysql', 'sqlite', 'mssql')
            config: Конфигурация подключения
            
        Returns:
            True если подключение успешно, иначе False
        """
        try:
            if engine == 'postgresql':
                return cls.test_postgresql(
                    config['host'], config['port'],
                    config['user'], config['password'],
                    config['name']
                )
            elif engine == 'mysql':
                return cls.test_mysql(
                    config['host'], config['port'],
                    config['user'], config['password'],
                    config['name']
                )
            elif engine == 'sqlite':
                return cls.test_sqlite(config['name'])
            elif engine == 'mssql':
                return cls.test_mssql(
                    config['host'], config['port'],
                    config['user'], config['password'],
                    config['name']
                )
            else:
                logger.error(f"Неизвестный тип БД: {engine}")
                return False
        except Exception as e:
            logger.error(f"Ошибка при тестировании подключения: {str(e)}")
            return False


# ==================== Класс для Django БД ====================

class DjangoDatabaseConfigLoader(BaseDatabaseConfigLoader):
    """
    Загрузчик конфигурации для Django DATABASES.
    Преобразует YAML конфигурацию в формат Django.
    """
    
    def __init__(self, system_dir: Path, resources_dir: Path, test_connections: bool = True):
        """
        Args:
            system_dir: Путь к корневой директории системы
            resources_dir: Путь к директории ресурсов
            test_connections: Тестировать ли подключения при загрузке
        """
        super().__init__(system_dir)
        self.resources_dir = resources_dir
        self.test_connections = test_connections
        self.connection_tester = DatabaseConnectionTester()
    
    def _build_django_config(self, db_name: str, db_config: Dict) -> Dict:
        """
        Строит конфигурацию БД в формате Django.
        
        Args:
            db_name: Имя БД
            db_config: Сырая конфигурация из YAML
            
        Returns:
            Конфигурация в формате Django
        """
        engine = db_config.get('engine', 'postgresql').lower()
        
        if engine not in DB_ENGINES:
            logger.error(f"Неподдерживаемый тип СУБД: {engine}")
            raise ValueError(f"Неподдерживаемый тип СУБД: {engine}")
        
        django_config = {
            'ENGINE': DB_ENGINES[engine],
            'NAME': db_config['name'],
        }
        
        # SQLite требует только путь к файлу
        if engine != 'sqlite':
            django_config.update({
                'USER': db_config['user'],
                'PASSWORD': db_config['password'],
                'HOST': db_config['host'],
                'PORT': db_config['port'],
            })
            
            # SSH туннель
            if 'ssh' in db_config:
                logger.info(f"Настройка SSH туннеля для БД '{db_name}'")
                django_config['SSH'] = {
                    'host': db_config['ssh'].get('host'),
                    'port': db_config['ssh'].get('port', 22),
                    'username': db_config['ssh'].get('username'),
                    'password': db_config['ssh'].get('password'),
                    'key_path': db_config['ssh'].get('key_path'),
                    'remote_host': db_config['host'],
                    'remote_port': db_config['port'],
                }
            
            # Специфичные настройки для СУБД
            if engine == 'mysql':
                django_config['OPTIONS'] = {
                    'init_command': "SET sql_mode='STRICT_TRANS_TABLES'",
                    'charset': 'utf8mb4',
                }
            elif engine == 'mssql':
                django_config['OPTIONS'] = {
                    'driver': 'ODBC Driver 17 for SQL Server',
                    'unicode_results': True,
                }
        
        return django_config
    
    def _get_fallback_sqlite_config(self) -> Dict:
        """Возвращает fallback конфигурацию SQLite"""
        return {
            'ENGINE': 'django.db.backends.sqlite3',
            'NAME': str(self.resources_dir / 'db.sqlite3'),
        }
    
    def _process_config(self, raw_config: Optional[Dict]) -> Dict:
        """
        Обрабатывает конфигурацию и преобразует в формат Django.
        
        Args:
            raw_config: Сырая конфигурация из YAML
            
        Returns:
            Конфигурация в формате Django DATABASES
        """
        if raw_config is None:
            logger.warning("Конфигурация не загружена, используется SQLite по умолчанию")
            return {'default': self._get_fallback_sqlite_config()}
        
        databases = {}
        
        for db_name, db_config in raw_config.items():
            try:
                django_config = self._build_django_config(db_name, db_config)
                
                # Тестируем подключение
                if self.test_connections:
                    engine = db_config.get('engine', 'postgresql').lower()
                    if self.connection_tester.test_connection(engine, db_config):
                        logger.info(f"Успешное подключение к БД '{db_name}' (тип: {DB_ENGINES[engine]})")
                        databases[db_name] = django_config
                    else:
                        logger.error(f"Не удалось подключиться к БД '{db_name}'")
                        # Для default используем fallback
                        if db_name == 'default':
                            databases[db_name] = self._get_fallback_sqlite_config()
                            logger.warning(f"БД '{db_name}' переключена на SQLite")
                else:
                    databases[db_name] = django_config
                    
            except Exception as e:
                logger.error(f"Ошибка при обработке БД '{db_name}': {str(e)}")
                if db_name == 'default':
                    databases[db_name] = self._get_fallback_sqlite_config()
        
        # Гарантируем наличие default
        if 'default' not in databases:
            logger.warning("Создано подключение SQLite по умолчанию")
            databases['default'] = self._get_fallback_sqlite_config()
        
        return databases


# ==================== Класс для Celery БД ====================

class CeleryDatabaseConfigLoader(BaseDatabaseConfigLoader):
    """
    Загрузчик конфигурации для Celery (broker и result backend).
    Поддерживает приоритеты секций и локальный режим.
    """
    
    def __init__(self, system_dir: Path, virtual_env_dir: Path, 
                 section_priorities: List[str], component_name: str = "Celery"):
        """
        Args:
            system_dir: Путь к корневой директории системы
            virtual_env_dir: Путь к виртуальному окружению
            section_priorities: Список секций в порядке приоритета (например, ['celery_worker', 'celery'])
            component_name: Имя компонента для логирования (например, "Celery Worker")
        """
        super().__init__(system_dir)
        self.virtual_env_dir = virtual_env_dir
        self.section_priorities = section_priorities
        self.component_name = component_name
        self.active_section: Optional[str] = None
        self.active_config: Optional[Dict] = None
    
    def _check_use_local_mode(self) -> bool:
        """Проверяет, нужно ли использовать локальный режим"""
        use_local = os.environ.get('CELERY_USE_LOCAL', 'false').lower() == 'true'
        if use_local:
            logger.info(f"{self.component_name}: Используется локальный режим по CELERY_USE_LOCAL")
        return use_local
    
    def _find_active_section(self) -> Optional[str]:
        """
        Находит активную секцию по приоритетам.

        Returns:
            Имя активной секции или None
        """
        available = self.get_available_sections()

        for section in self.section_priorities:
            if section in available:
                logger.info(f"{self.component_name}: Используется секция '{section}'")
                return section

        return None
    
    def _get_local_sqlite_urls(self, *, log_reason: Optional[str] = None) -> Tuple[str, str]:
        """
        Возвращает URLs для локального SQLite.
        log_reason: если задан, логирует одну строку вместо двух ('не найдена' + 'локальный SQLite').
        """
        celery_dir = self.virtual_env_dir / 'celery'
        celery_dir.mkdir(parents=True, exist_ok=True)
        
        broker_url = f'sqla+sqlite:///{self.virtual_env_dir}/celery/celerydb.sqlite'
        result_backend = f'db+sqlite:///{self.virtual_env_dir}/celery/results.sqlite'
        
        if log_reason:
            logger.info(f"{self.component_name}: {log_reason}, используется локальный SQLite")
        else:
            logger.info(f"{self.component_name}: Используется локальный SQLite")
        return broker_url, result_backend
    
    def _build_celery_urls(self, db_config: Dict) -> Tuple[str, str]:
        """
        Строит URLs для Celery broker и result backend.
        
        Args:
            db_config: Конфигурация БД
            
        Returns:
            Tuple (broker_url, result_backend)
        """
        engine = db_config.get('engine', 'postgresql').lower()
        
        # Проверяем обязательные поля
        host = db_config.get('host', '').strip()
        if not host:
            logger.warning(
                f"{self.component_name}: Host не указан в конфигурации БД, "
                "используется локальный SQLite"
            )
            return self._get_local_sqlite_urls()
        
        # Экранируем credentials
        user = quote_plus(db_config.get('user', ''))
        password = quote_plus(db_config.get('password', ''))
        port = db_config.get('port', 5432 if engine == 'postgresql' else 3306)
        name = db_config.get('name', '')
        
        if not name:
            logger.warning(
                f"{self.component_name}: Имя БД не указано в конфигурации, "
                "используется локальный SQLite"
            )
            return self._get_local_sqlite_urls()
        
        if engine == 'postgresql':
            broker_url = f"sqla+postgresql://{user}:{password}@{host}:{port}/{name}"
            result_backend = f"db+postgresql://{user}:{password}@{host}:{port}/{name}"
        elif engine == 'mysql':
            broker_url = f"sqla+mysql://{user}:{password}@{host}:{port}/{name}"
            result_backend = f"db+mysql://{user}:{password}@{host}:{port}/{name}"
        elif engine == 'sqlite':
            db_path = name
            broker_url = f'sqla+sqlite:///{db_path}'
            result_backend = f'db+sqlite:///{db_path}'
        else:
            logger.warning(f"{self.component_name}: Неподдерживаемый тип БД '{engine}'")
            return self._get_local_sqlite_urls()
        
        logger.info(f"{self.component_name}: Настроена работа с {engine} БД ({host}:{port}/{name})")
        return broker_url, result_backend
    
    def _process_config(self, raw_config: Optional[Dict]) -> Dict:
        """
        Обрабатывает конфигурацию и возвращает URLs для Celery.
        
        Returns:
            Dict с broker_url, result_backend и metadata
        """
        # Проверяем локальный режим
        if self._check_use_local_mode():
            broker_url, result_backend = self._get_local_sqlite_urls()
            return {
                'broker_url': broker_url,
                'result_backend': result_backend,
                'mode': 'local',
                'section': None,
            }
        
        # Проверяем доступность конфигурации
        if raw_config is None:
            broker_url, result_backend = self._get_local_sqlite_urls()
            return {
                'broker_url': broker_url,
                'result_backend': result_backend,
                'mode': 'local',
                'section': None,
            }
        
        # Находим активную секцию
        self.active_section = self._find_active_section()

        if self.active_section is None:
            priorities = self.section_priorities
            broker_url, result_backend = self._get_local_sqlite_urls(
                log_reason=f"Ни одна из секций {priorities} не найдена"
            )
            return {
                'broker_url': broker_url,
                'result_backend': result_backend,
                'mode': 'local',
                'section': None,
            }
        
        # Получаем конфигурацию секции
        self.active_config = raw_config[self.active_section]
        if self.active_config is None:
            broker_url, result_backend = self._get_local_sqlite_urls()
            return {
                'broker_url': broker_url,
                'result_backend': result_backend,
                'mode': 'local',
                'section': None,
            }
        
        broker_url, result_backend = self._build_celery_urls(self.active_config)
        
        return {
            'broker_url': broker_url,
            'result_backend': result_backend,
            'mode': 'database',
            'section': self.active_section,
            'engine': self.active_config.get('engine', 'postgresql'),
        }
    
    def get_active_section(self) -> Optional[str]:
        """
        Возвращает имя активной секции БД.
        
        Returns:
            Имя секции или None, если используется локальный режим
        """
        if self.active_section is None:
            # Если секция еще не определена, загружаем конфигурацию
            self.load_config()
        return self.active_section
    
    def get_django_db_alias(self) -> Optional[str]:
        """
        Возвращает alias Django БД для django-celery-beat.
        Использует БД, указанную в конфиге согласно приоритетам секций.
        Для celery beat это может быть: celery_beat -> celery -> локальный SQLite
        
        Returns:
            Alias БД или None для локального режима
        """
        config = self.load_config()
        
        if config['mode'] == 'local':
            return None
        
        # Возвращаем секцию из конфига (celery_beat, celery и т.д.)
        # Система автоматически выбирает правильную БД по приоритетам
        return config['section']

