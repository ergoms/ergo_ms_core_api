"""
Настройка поля автоинкремента по умолчанию для моделей Django.
Используется BigAutoField для автоматического создания больших целочисленных полей.
"""
from typing import Optional

from django.conf import settings

from sshtunnel import SSHTunnelForwarder

import socket

from typing import Dict, Optional

import logging

logger = logging.getLogger('utils')

class SSHConnection:
    """
    Класс для управления SSH-туннелем
    """
    def __init__(self, ssh_config: dict) -> None:
        self.ssh_host = ssh_config.get('host')
        self.ssh_port = ssh_config.get('port', 22)
        self.ssh_username = ssh_config.get('username')
        self.ssh_password = ssh_config.get('password')
        self.ssh_key = ssh_config.get('key_path')
        self.remote_host = ssh_config.get('remote_host')
        self.remote_port = ssh_config.get('remote_port')
        self.local_port = self._find_free_port()
        self._tunnel = None

    def _find_free_port(self) -> int:
        """Находит свободный порт на локальной машине"""
        with socket.socket() as s:
            s.bind(('', 0))
            return s.getsockname()[1]

    def __enter__(self) -> SSHTunnelForwarder:
        if not self.ssh_host:
            logger.warning("SSH хост не указан, туннель не будет создан")
            return None

        try:
            ssh_config = {
                'ssh_address_or_host': (self.ssh_host, self.ssh_port),
                'remote_bind_address': (self.remote_host, self.remote_port),
                'local_bind_address': ('127.0.0.1', self.local_port),
            }

            if self.ssh_key:
                ssh_config['ssh_pkey'] = self.ssh_key
            else:
                ssh_config['ssh_username'] = self.ssh_username
                ssh_config['ssh_password'] = self.ssh_password

            self._tunnel = SSHTunnelForwarder(**ssh_config)
            self._tunnel.start()
            logger.info(f"SSH туннель успешно создан к {self.ssh_host}:{self.ssh_port}")
            return self._tunnel
        except Exception as e:
            logger.error(f"Ошибка при создании SSH туннеля: {str(e)}")
            raise

    def __exit__(self, exc_type, exc_val, exc_tb):
        if self._tunnel:
            try:
                self._tunnel.close()
                logger.info("SSH туннель успешно закрыт")
            except Exception as e:
                logger.error(f"Ошибка при закрытии SSH туннеля: {str(e)}")

class DBConfig:
    """
    Конфигурация для работы с определенной базой данных
    """
    def __init__(self, db_name: str = 'default') -> None:
        self.db_config = settings.DATABASES[db_name]
        self.ENGINE = self.db_config['ENGINE']
        self.DB_NAME = self.db_config['NAME']
        self.ssh_tunnel: Optional[SSHConnection] = None
        
        # Для не-SQLite баз данных
        if 'sqlite3' not in self.ENGINE:
            self.USERNAME = self.db_config['USER']
            self.PASSWORD = self.db_config['PASSWORD']
            self.HOST = self.db_config['HOST']
            self.PORT = self.db_config['PORT']
            
            # Инициализация SSH туннеля если он настроен
            if 'SSH' in self.db_config:
                self.ssh_tunnel = SSHConnection(self.db_config['SSH'])

    def __enter__(self):
        if self.ssh_tunnel:
            tunnel = self.ssh_tunnel.__enter__()
            if tunnel:
                self.HOST = '127.0.0.1'
                self.PORT = self.ssh_tunnel.local_port
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        if self.ssh_tunnel:
            self.ssh_tunnel.__exit__(exc_type, exc_val, exc_tb)

    def __repr__(self) -> str:
        return self.get_url()

    def get_url(self):
        """
        Получает URL подключения в зависимости от типа СУБД
        """
        if 'postgresql' in self.ENGINE:
            return self.POSTGRESQL_URL
        elif 'mysql' in self.ENGINE:
            return self.MYSQL_URL
        elif 'sqlite3' in self.ENGINE:
            return self.SQLITE_URL
        elif 'mssql' in self.ENGINE:
            return self.MSSQL_URL
        return None

    @property
    def SQLALCHEMY_URL(self):
        """
        URL для SQLAlchemy
        """
        if 'sqlite3' in self.ENGINE:
            return f"sqlite:///{self.DB_NAME}"
        elif 'mssql' in self.ENGINE:
            return f"mssql+pyodbc://{self.USERNAME}:{self.PASSWORD}@{self.HOST}:{self.PORT}/{self.DB_NAME}?driver=ODBC+Driver+17+for+SQL+Server"
        return f"postgresql+psycopg2://{self.USERNAME}:{self.PASSWORD}@{self.HOST}:{self.PORT}/{self.DB_NAME}"

    @property
    def POSTGRESQL_URL(self):
        return f"postgresql://{self.USERNAME}:{self.PASSWORD}@{self.HOST}:{self.PORT}/{self.DB_NAME}"

    @property
    def MYSQL_URL(self):
        return f"mysql://{self.USERNAME}:{self.PASSWORD}@{self.HOST}:{self.PORT}/{self.DB_NAME}"

    @property
    def SQLITE_URL(self):
        return f"sqlite:///{self.DB_NAME}"

    @property
    def MSSQL_URL(self):
        return f"mssql://{self.USERNAME}:{self.PASSWORD}@{self.HOST}:{self.PORT}/{self.DB_NAME}"