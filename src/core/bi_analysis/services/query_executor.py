from src.core.bi_analysis.bi_connections.connectors.postgres import get_pg_engine
from src.core.bi_analysis.bi_connections.connectors.mssql import get_mssql_engine
from src.core.bi_analysis.bi_connections.connectors.clickhouse import get_clickhouse_client

def run_pg_query(query: str):
    with get_pg_engine().connect() as conn:
        return conn.execute(query).fetchall()

def run_mssql_query(query: str):
    with get_mssql_engine().connect() as conn:
        return conn.execute(query).fetchall()

def run_clickhouse_query(query: str):
    client = get_clickhouse_client()
    return client.query(query).result_rows