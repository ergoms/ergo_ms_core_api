import clickhouse_connect
import psycopg2
import pymssql
import traceback

class CheckConnection:
    @staticmethod
    def check_clickhouse(host, port, username, password):
        try:
            client = clickhouse_connect.get_client(host=host, port=port, username=username, password=password)
            client.query('SELECT 1')
            return True, "Соединение с ClickHouse установлено"
        except Exception as e:
            return False, str(e)

    @staticmethod
    def check_postgresql(host, port, username, password, dbname='postgres'):
        try:
            conn = psycopg2.connect(
                host=host,
                port=port,
                user=username,
                password=password,
                dbname=dbname
            )
            conn.close()
            return True, "Соединение с PostgreSQL установлено"
        except Exception as e:
            messages = []
            for arg in e.args:
                if isinstance(arg, bytes):
                    try:
                        decoded = arg.decode('cp1251', errors='replace')
                        messages.append(decoded)
                    except Exception:
                        messages.append(repr(arg))
                else:
                    messages.append(str(arg))
            return False, ' '.join(messages).strip()

    @staticmethod
    def check_mssql(host, port, username, password, database):
        try:
            conn = pymssql.connect(
                server=host,
                port=port,
                user=username,
                password=password,
                database=database
            )
            conn.close()
            return True, "Соединение с MSSQL установлено"
        except Exception as e:
            return False, str(e)